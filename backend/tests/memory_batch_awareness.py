"""
Cross-batch awareness slice (`BatchAwarenessPort`) — `core/memory/batch_store.py`
(Qdrant mechanics) + `core/memory/batch_awareness_manager.py` (the sole
implementer: status-priority truncation, self-exclusion, and the poll-based
`clear_mission` sweep).

Ratified 2026-07-05 (`proposals/archive/to-backend/2026-07-05_cross-batch-
awareness-memory-design.md`, ruling in `archive/to-memory/2026-07-05_cross-
batch-design-ratified.md`); built 2026-07-06 once the Mission Engine (§9) and
the foundation contract (`foundation/contracts/batch_awareness.py`) landed.

Qdrant-touching tests are gated behind a real, reachable Qdrant instance
(same `_qdrant_up()` skip convention as `tests/memory_isolation.py` — this
repo's tests never mock Qdrant's wire protocol). The sweep-DECISION logic
(does this mission look terminal?) is tested hermetically: the graph half is
real embedded Kuzu (always available, no skip needed), and `batch_store.
clear_mission` is monkeypatched to a recorder so the sweep's own branching
logic is provable without a live Qdrant.

  ✓ BatchAwarenessItem's field set is exactly the five ratified fields
    (schema-minimality, mirrors c4_decision_memory.py's own pin)
  ✓ hard key-upsert: two status writes for the same (user_id, mission_id,
    batch_id) with very different headlines collapse to ONE point, old
    status gone — not the cosine-dedup soft-merge store.upsert uses
  ✓ tenant isolation: two users with the identical (mission_id, batch_id)
    never see or overwrite each other's status
  ✓ self-exclusion: requesting_batch_id never appears in its own slice
  ✓ truncation prioritizes BLOCKED/FAILED over recency — a stale blocked
    batch survives, a very-recent active one is what gets dropped
  ✓ the aggregate size bound holds as batch count grows well past the cap,
    with a non-silent notes signal
  ✓ degrade-never-fail when the store is unavailable, hermetically
  ✓ right-to-erasure (delete_user) reaches this collection
  ✓ clear_mission removes only the target mission's points
  ✓ the poll-on-read sweep condition: fires on a terminal MISSION status,
    not on a non-terminal one — proven against real Kuzu, batch_store calls
    mocked so no live Qdrant is required for this half
  ✓ the periodic-backstop sweep finds every terminal mission for a user

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_batch_awareness.py -v
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import urllib.request

import pytest

import core.memory.batch_store as batch_store
from core.memory.batch_awareness_manager import BatchAwarenessManager
from core.memory.graph_manager import manager as graph_manager
from foundation import BatchAwarenessItem, BatchAwarenessPort, BatchLifecycleStatus, GraphNode, GraphScope, NodeLabel


def _qdrant_up() -> bool:
    try:
        urllib.request.urlopen(os.getenv("QDRANT_URL", "http://localhost:6333") + "/readyz", timeout=2)
        return True
    except Exception:
        return False


_needs_qdrant = pytest.mark.skipif(not _qdrant_up(), reason="qdrant not reachable")


@pytest.fixture
def bam() -> BatchAwarenessManager:
    return BatchAwarenessManager()


def _mission_node(scope: GraphScope, mission_id: str, status: str) -> GraphNode:
    from core.memory import graph_store
    return GraphNode(
        node_id=graph_store.node_id(scope, mission_id), label=NodeLabel.MISSION, scope=scope,
        properties={"mission_id": mission_id, "intent": "ship it", "success_criteria": ["a"], "status": status,
                    "updated_at": 1.0},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schema + isinstance
# ─────────────────────────────────────────────────────────────────────────────

def test_batch_awareness_manager_satisfies_the_port(bam):
    assert isinstance(bam, BatchAwarenessPort)


def test_batch_awareness_item_schema_minimality():
    item = BatchAwarenessItem(batch_id="b1", domain="d", status=BatchLifecycleStatus.ACTIVE, headline="h")
    assert {f for f in item.__dataclass_fields__} == {"batch_id", "domain", "status", "headline", "updated_at"}


# ─────────────────────────────────────────────────────────────────────────────
# Hermetic (no live Qdrant needed)
# ─────────────────────────────────────────────────────────────────────────────

def test_record_batch_status_refuses_on_missing_ids_before_touching_the_store(bam):
    async def go():
        assert await bam.record_batch_status("", "m1", "b1", "d", BatchLifecycleStatus.ACTIVE, "h") is False
        assert await bam.record_batch_status("u1", "", "b1", "d", BatchLifecycleStatus.ACTIVE, "h") is False
        assert await bam.record_batch_status("u1", "m1", "", "d", BatchLifecycleStatus.ACTIVE, "h") is False
    asyncio.run(go())


def test_cross_batch_awareness_fail_closed_on_missing_ids(bam):
    async def go():
        result = await bam.cross_batch_awareness("", "m1", "b0")
        assert result.degraded is True
        result = await bam.cross_batch_awareness("u1", "", "b0")
        assert result.degraded is True
    asyncio.run(go())


def test_cross_batch_awareness_degrades_when_store_down(bam, monkeypatch):
    monkeypatch.setattr(
        batch_store, "scroll_batch_statuses",
        lambda user_id, mission_id: batch_store.BatchStatusReadResult(degraded=True, notes="batch store unavailable"),
    )
    async def go():
        result = await bam.cross_batch_awareness("u1", "m1", "b0")
        assert result.degraded is True
    asyncio.run(go())


def test_sweep_if_terminal_fires_on_a_terminal_mission_status(bam, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_store, "clear_mission", lambda user_id, mission_id: calls.append((user_id, mission_id)))
    async def go():
        scope = GraphScope(user_id="u1")
        await graph_manager.write(scope, [_mission_node(scope, "m1", "done")], [])
        swept = await bam._sweep_if_terminal("u1", "m1")
        assert swept is True
        assert calls == [("u1", "m1")]
    asyncio.run(go())


def test_sweep_if_terminal_does_not_fire_on_an_active_mission(bam, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_store, "clear_mission", lambda user_id, mission_id: calls.append((user_id, mission_id)))
    async def go():
        scope = GraphScope(user_id="u1")
        await graph_manager.write(scope, [_mission_node(scope, "m1", "active")], [])
        swept = await bam._sweep_if_terminal("u1", "m1")
        assert swept is False
        assert calls == []
    asyncio.run(go())


def test_sweep_if_terminal_does_not_fire_when_mission_node_is_absent(bam, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_store, "clear_mission", lambda user_id, mission_id: calls.append((user_id, mission_id)))
    async def go():
        swept = await bam._sweep_if_terminal("u1", "never-written")
        assert swept is False
        assert calls == []
    asyncio.run(go())


def test_sweep_terminal_missions_backstop_finds_every_terminal_mission(bam, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_store, "clear_mission", lambda user_id, mission_id: calls.append((user_id, mission_id)))
    async def go():
        scope = GraphScope(user_id="u1")
        await graph_manager.write(scope, [
            _mission_node(scope, "m1", "done"),
            _mission_node(scope, "m2", "active"),
            _mission_node(scope, "m3", "failed"),
        ], [])
        swept = await bam.sweep_terminal_missions("u1")
        assert swept == 2
        assert set(calls) == {("u1", "m1"), ("u1", "m3")}
    asyncio.run(go())


def test_sweep_terminal_missions_is_a_noop_on_missing_user_id(bam, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_store, "clear_mission", lambda user_id, mission_id: calls.append((user_id, mission_id)))
    async def go():
        assert await bam.sweep_terminal_missions("") == 0
        assert calls == []
    asyncio.run(go())


def test_ensure_concurrent_cold_start_creates_the_collection_exactly_once(monkeypatch):
    """Widen `_ensure`'s check-then-act window and prove `_ensure_lock` actually
    serializes it — mirrors `memory_graph_store.py`'s identical proof for
    `graph_store._kuzu`'s lock. Regression for a real gap caught in review:
    `_ensure`'s docstring claimed it reused `store`'s lock via `store.
    connection()`, but `connection()` acquires-and-releases that lock before
    returning, so `_ensure` originally ran completely unlocked. Hermetic (a
    fake client), so this proves the fix without needing live Qdrant."""
    monkeypatch.setattr(batch_store, "_ensured", False)
    calls = {"n": 0}
    count_lock = threading.Lock()

    class _FakeClient:
        def collection_exists(self, name):
            return False

        def create_collection(self, *a, **k):
            with count_lock:
                calls["n"] += 1
            time.sleep(0.05)  # widen the race window

        def create_payload_index(self, *a, **k):
            pass

    client = _FakeClient()

    async def go():
        return await asyncio.gather(
            *(asyncio.to_thread(batch_store._ensure, client) for _ in range(10)),
            return_exceptions=True,
        )

    results = asyncio.run(go())
    assert not any(isinstance(r, BaseException) for r in results), (
        f"a concurrent cold start must never raise: {results}"
    )
    assert all(results), "every concurrent caller must still see success"
    assert calls["n"] == 1, (
        f"create_collection must be called exactly once under a concurrent "
        f"cold start, got {calls['n']} — the lock isn't serializing callers"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Qdrant-gated (real store round-trip)
# ─────────────────────────────────────────────────────────────────────────────

@_needs_qdrant
def test_hard_key_upsert_not_soft_merge(bam):
    """Two writes to the same (user_id, mission_id, batch_id) with very
    different headlines (so cosine similarity would NOT trigger the
    existing dedup path even if this went through it) must collapse to ONE
    point, old status gone."""
    async def go():
        try:
            ok1 = await bam.record_batch_status("u-hku", "m1", "b1", "docs", BatchLifecycleStatus.ACTIVE, "starting up")
            ok2 = await bam.record_batch_status("u-hku", "m1", "b1", "docs", BatchLifecycleStatus.BLOCKED, "totally different text, blocked on X")
            assert ok1 and ok2
            result = await bam.cross_batch_awareness("u-hku", "m1", "")
            assert len(result.items) == 1
            assert result.items[0].status == BatchLifecycleStatus.BLOCKED
            assert result.items[0].headline == "totally different text, blocked on X"
        finally:
            batch_store.delete_user("u-hku")
    asyncio.run(go())


@_needs_qdrant
def test_tenant_isolation_same_mission_and_batch_id_different_user(bam):
    async def go():
        try:
            await bam.record_batch_status("u-a", "m1", "b1", "docs", BatchLifecycleStatus.ACTIVE, "user A's batch")
            await bam.record_batch_status("u-b", "m1", "b1", "docs", BatchLifecycleStatus.ACTIVE, "user B's batch")
            a_view = await bam.cross_batch_awareness("u-a", "m1", "")
            b_view = await bam.cross_batch_awareness("u-b", "m1", "")
            assert len(a_view.items) == 1 and a_view.items[0].headline == "user A's batch"
            assert len(b_view.items) == 1 and b_view.items[0].headline == "user B's batch"
        finally:
            batch_store.delete_user("u-a")
            batch_store.delete_user("u-b")
    asyncio.run(go())


@_needs_qdrant
def test_self_exclusion_requesting_batch_never_in_its_own_slice(bam):
    async def go():
        try:
            await bam.record_batch_status("u-self", "m1", "b1", "docs", BatchLifecycleStatus.ACTIVE, "b1")
            await bam.record_batch_status("u-self", "m1", "b2", "docs", BatchLifecycleStatus.ACTIVE, "b2")
            result = await bam.cross_batch_awareness("u-self", "m1", "b1")
            assert {i.batch_id for i in result.items} == {"b2"}
        finally:
            batch_store.delete_user("u-self")
    asyncio.run(go())


@_needs_qdrant
def test_truncation_prioritizes_status_over_recency(bam):
    async def go():
        user = "u-trunc"
        try:
            # one long-stale BLOCKED batch...
            await bam.record_batch_status(user, "m1", "stale-blocked", "docs", BatchLifecycleStatus.BLOCKED, "been stuck a while")
            # ...plus MAX_BATCHES_PER_MISSION very-recently-updated ACTIVE batches
            for i in range(batch_store.MAX_BATCHES_PER_MISSION):
                await bam.record_batch_status(user, "m1", f"active-{i}", "docs", BatchLifecycleStatus.ACTIVE, f"active {i}")

            result = await bam.cross_batch_awareness(user, "m1", "")

            assert result.total_batches == batch_store.MAX_BATCHES_PER_MISSION + 1
            assert len(result.items) == batch_store.MAX_BATCHES_PER_MISSION
            assert "stale-blocked" in {i.batch_id for i in result.items}, (
                "the stale BLOCKED batch must survive truncation over a wave of recent ACTIVE ones"
            )
            assert result.notes and "omitted" in result.notes
        finally:
            batch_store.delete_user(user)
    asyncio.run(go())


@_needs_qdrant
def test_aggregate_size_bound_holds_as_batch_count_grows(bam):
    """Not just a count check — the quantified aggregate (§4 of the ratified
    design) must hold even with maximally-long headlines, well past the cap."""
    user = "u-bound"
    try:
        long_headline = "x" * 1000  # far past _HEADLINE_CHAR_CAP=200
        async def seed():
            for i in range(120):
                await bam.record_batch_status(user, "m1", f"b{i}", "docs", BatchLifecycleStatus.ACTIVE, long_headline)
        asyncio.run(seed())

        result = asyncio.run(bam.cross_batch_awareness(user, "m1", ""))
        assert result.total_batches == 120
        assert len(result.items) == batch_store.MAX_BATCHES_PER_MISSION
        total_chars = sum(len(i.headline) for i in result.items)
        assert total_chars <= batch_store.MAX_BATCHES_PER_MISSION * 200
        assert all(len(i.headline) <= 200 for i in result.items)
    finally:
        batch_store.delete_user(user)


@_needs_qdrant
def test_delete_user_purges_batch_status(bam):
    async def go():
        await bam.record_batch_status("u-erase", "m1", "b1", "docs", BatchLifecycleStatus.ACTIVE, "h")
        await bam.delete_user("u-erase")
        result = await bam.cross_batch_awareness("u-erase", "m1", "")
        assert result.items == []
    asyncio.run(go())


@_needs_qdrant
def test_clear_mission_purges_only_the_target_mission(bam):
    async def go():
        user = "u-clear"
        try:
            await bam.record_batch_status(user, "m1", "b1", "docs", BatchLifecycleStatus.ACTIVE, "h")
            await bam.record_batch_status(user, "m2", "b1", "docs", BatchLifecycleStatus.ACTIVE, "h")
            batch_store.clear_mission(user, "m1")
            assert (await bam.cross_batch_awareness(user, "m1", "")).items == []
            assert len((await bam.cross_batch_awareness(user, "m2", "")).items) == 1
        finally:
            batch_store.delete_user(user)
    asyncio.run(go())
