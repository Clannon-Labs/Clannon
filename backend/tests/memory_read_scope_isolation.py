"""
Hermetic harness pinning the READ-path tenant-isolation invariant (§V.20).

tests/memory_isolation.py pins the WRITE path (cross-user upsert refusal,
Qdrant index structure) against a live Qdrant instance and skips when none is
reachable.  This file pins the READ path using a test-double store that needs
no network and no paid keys.

Model under test
----------------
  * Two synthetic users' records are seeded into a shared in-memory store
    double that mirrors the single-Qdrant + user_id payload-filter model
    (ADR 0002 / §V.20): ALL users' data lives in one backing dict, and
    search() filters by user_id exactly as _user_filter() does in the real
    store.
  * SEQUENTIAL and CONCURRENT interleaved hydrate() calls are issued for both
    users.
  * Each call must return ONLY that user's own records.  No record authored
    under user A may appear in user B's hydration result, including under
    interleaving.
  * The empty / missing user_id path must fail closed: store.search must never
    be called, and the returned package must be empty.

Output
------
Each test prints a per-user records-returned vs cross-leak table with a
"scoped / LEAK" verdict.  If a genuine cross-user leak is detected the test
also writes a needs-reviewer note to /home/amrit/.clannon_proposal and fails
with a SECURITY GAP message rather than attempting to patch the door.

Invariant pinned
----------------
§V.20 (ADR 0002): user_id payload filter is the sole read-path scope; the
MemoryManager is the only door.

Serves: Critical Benchmark 1 (C1, retrieval scoping) and
        Critical Benchmark 5 (C5, memory-isolation guarantee).
"""

from __future__ import annotations

import asyncio
import pathlib
import threading
import time
from typing import Any

import pytest

from foundation import (
    HydrationPackage,
    HydrationRequest,
    MemoryStore,
    NormalizedInput,
)
from core.memory.manager import MemoryManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fixed vector used for all queries -- deterministic, no real embedding model.
_DIMS = 768
_VEC: list[float] = [0.0] * (_DIMS - 1) + [1.0]

# Score well above the 0.30 relevance floor so hits always pass the manager's
# floor check (manager.py:151-156).
_SCORE = 0.95

# created_at=0 means epoch 1970; recency decay collapses to the floor (0.5),
# giving rank_score = 0.95 * 0.5 = 0.475 -- still positive, still returned.
_CREATED_AT = 0.0

_USER_A = "tenant-alice-00001"
_USER_B = "tenant-bob-00002"

# Records embed the owner's user_id so the audit can distinguish them without
# out-of-band bookkeeping.  The marker mirrors what a real memory write would
# look like after episodic distillation ("user <id> noted: ...").
_ALICE_CONTENTS = [
    f"[{_USER_A}] the kiwi codename",
    f"[{_USER_A}] prefers terse reports",
]
_BOB_CONTENTS = [
    f"[{_USER_B}] the mango codename",
    f"[{_USER_B}] prefers detailed reports",
]

_NEEDS_REVIEWER_PATH = pathlib.Path("/home/amrit/.clannon_proposal")


# ---------------------------------------------------------------------------
# In-memory store double — the single-Qdrant + user_id payload-filter model
# ---------------------------------------------------------------------------


class _StoreDouble:
    """Simulates a single shared Qdrant instance with user_id payload filtering.

    All users' records live in one backing dict, keyed by (tier, user_id),
    exactly as Qdrant physically groups points by tenant.  search() applies
    the user_id payload filter, mirroring store._user_filter(user_id).

    search_log records every (tier, user_id) call so tests can verify the
    manager never queries with the wrong user_id.  A threading.Lock guards
    the log because manager.hydrate() dispatches search() calls via
    asyncio.to_thread -- they arrive from multiple worker threads concurrently.
    """

    def __init__(self) -> None:
        self._data: dict[tuple[MemoryStore, str], list[dict[str, Any]]] = {}
        self.search_log: list[tuple[MemoryStore, str]] = []
        self._lock = threading.Lock()

    def seed(self, tier: MemoryStore, user_id: str, contents: list[str]) -> None:
        key = (tier, user_id)
        self._data.setdefault(key, [])
        for idx, content in enumerate(contents):
            self._data[key].append({
                "id": f"{user_id}-{tier.value}-{idx}",
                "user_id": user_id,
                "score": _SCORE,
                "content": content,
                "created_at": _CREATED_AT,
            })

    def search(
        self,
        tier: MemoryStore,
        user_id: str,
        vector: list[float],  # noqa: ARG002 — content-based store, vector ignored
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return only records for user_id — the sole §V.20 invariant."""
        with self._lock:
            self.search_log.append((tier, user_id))
        return self._data.get((tier, user_id), [])[:limit]

    def is_down(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(text: str) -> NormalizedInput:
    return NormalizedInput(modality="text", content_type="text/plain", content=text)


def _hydrate_req(user_id: str, session_id: str = "s") -> HydrationRequest:
    return HydrationRequest(
        session_id=session_id,
        user_id=user_id,
        normalized=_norm("query"),
        token_budget=4000,
    )


def _audit(pkg: HydrationPackage, owner: str, other: str) -> dict[str, Any]:
    """Classify one hydration result for the report table."""
    own_items = [i for i in pkg.items if owner in i.content]
    leaked = [i for i in pkg.items if other in i.content]
    return {
        "user": owner,
        "returned": len(pkg.items),
        "own": len(own_items),
        "cross_leak": len(leaked),
        "leaked_contents": [i.content for i in leaked],
        "verdict": "LEAK" if leaked else "scoped",
    }


def _report_table(rows: list[dict]) -> None:
    hdr = f"{'user_id':<22} {'call#':>5} {'returned':>10} {'own':>5} {'cross-leak':>12} {'verdict':>8}"
    sep = "-" * len(hdr)
    print(f"\n{sep}")
    print(hdr)
    print(sep)
    for r in rows:
        print(
            f"{r['user']:<22} {r['call']:>5} {r['returned']:>10}"
            f" {r['own']:>5} {r['cross_leak']:>12} {r['verdict']:>8}"
        )
    print(sep)
    leaks = [r for r in rows if r["verdict"] == "LEAK"]
    if leaks:
        print(f"\n*** SECURITY GAP DETECTED: {len(leaks)} cross-user leak(s) ***")
        for r in leaks:
            for content in r["leaked_contents"]:
                print(f"    user={r['user']} call={r['call']}: leaked record -> {content!r}")
        _file_needs_reviewer(leaks)
    else:
        print("\nAll calls: scoped -- no cross-user leak detected.")
    print()


def _file_needs_reviewer(leaks: list[dict]) -> None:
    """Write a needs-reviewer note when a genuine cross-user leak is found.

    The harness does NOT patch the door -- it reports the gap and fails.
    This file is monitored by the curator loop (goal_journal.md §V).
    """
    lines = [
        f"needs-reviewer: cross-user memory READ leak detected at {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "test: backend/tests/memory_read_scope_isolation.py",
        "invariant: §V.20 (ADR 0002) -- user_id payload filter on hydrate() READ path",
        "benchmarks: C1 retrieval scoping, C5 memory-isolation guarantee",
        "",
        "Leaked records:",
    ]
    for r in leaks:
        for content in r["leaked_contents"]:
            lines.append(f"  user={r['user']} call={r['call']}: {content!r}")
    lines += [
        "",
        "Options:",
        "  1. Verify store.search correctly applies _user_filter() on every call.",
        "  2. Check manager.hydrate() passes request.user_id (not a stale local) to store.search.",
        "  3. Verify asyncio.gather() result ordering is not mixed between concurrent hydrate() calls.",
        "",
        "Do NOT patch the door in this harness -- the gap is in manager.py or store.py.",
    ]
    try:
        _NEEDS_REVIEWER_PATH.write_text("\n".join(lines) + "\n")
    except OSError:
        pass  # best-effort; the assertion failure below is the authoritative signal


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_double(monkeypatch: pytest.MonkeyPatch) -> _StoreDouble:
    """Wire a fresh store double + a no-op async embedder into the manager."""
    double = _StoreDouble()
    double.seed(MemoryStore.EPISODIC, _USER_A, _ALICE_CONTENTS)
    double.seed(MemoryStore.EPISODIC, _USER_B, _BOB_CONTENTS)

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [_VEC[:] for _ in texts]

    monkeypatch.setattr("core.memory.store.search", double.search)
    monkeypatch.setattr("core.memory.store.is_down", double.is_down)
    monkeypatch.setattr("core.memory.embeddings.embed", _fake_embed)
    return double


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSingleUserBaseline:
    """Baseline: a single hydrate() call sees only its own user's records."""

    def test_user_a_sees_only_own_records(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()
        pkg = asyncio.run(manager.hydrate(_hydrate_req(_USER_A)))

        row = {**_audit(pkg, _USER_A, _USER_B), "call": 1}
        _report_table([row])

        assert row["cross_leak"] == 0, (
            f"SECURITY GAP: user A's hydration returned user B record(s): "
            f"{row['leaked_contents']}"
        )
        assert row["own"] > 0, "user A must receive at least one of her own records"

    def test_user_b_sees_only_own_records(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()
        pkg = asyncio.run(manager.hydrate(_hydrate_req(_USER_B)))

        row = {**_audit(pkg, _USER_B, _USER_A), "call": 1}
        _report_table([row])

        assert row["cross_leak"] == 0, (
            f"SECURITY GAP: user B's hydration returned user A record(s): "
            f"{row['leaked_contents']}"
        )
        assert row["own"] > 0, "user B must receive at least one of her own records"


class TestSequentialInterleaving:
    """A-B-A-B sequential interleaving -- no cross-user leak in any call."""

    def test_interleaved_sequential_no_leak(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()

        async def run() -> list[tuple[HydrationRequest, HydrationPackage]]:
            reqs = [
                _hydrate_req(_USER_A, "s1"),
                _hydrate_req(_USER_B, "s2"),
                _hydrate_req(_USER_A, "s3"),
                _hydrate_req(_USER_B, "s4"),
            ]
            results = []
            for req in reqs:
                pkg = await manager.hydrate(req)
                results.append((req, pkg))
            return results

        pairs = asyncio.run(run())
        rows = []
        for call_idx, (req, pkg) in enumerate(pairs, 1):
            other = _USER_B if req.user_id == _USER_A else _USER_A
            rows.append({**_audit(pkg, req.user_id, other), "call": call_idx})

        _report_table(rows)

        for row in rows:
            assert row["cross_leak"] == 0, (
                f"SECURITY GAP: sequential call #{row['call']} for {row['user']} "
                f"leaked {row['cross_leak']} record(s): {row['leaked_contents']}"
            )
            assert row["own"] > 0, (
                f"call #{row['call']} for {row['user']} returned no own records"
            )


class TestConcurrentInterleaving:
    """asyncio.gather concurrent interleaving -- the tightest isolation check.

    All four hydrate() coroutines run simultaneously in one event loop.  If
    any shared state in MemoryManager carried user_id between concurrent calls,
    or if asyncio.gather result ordering mixed results across calls, the
    content-based audit would catch it.
    """

    def test_interleaved_concurrent_no_leak(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()

        async def run() -> list[tuple[HydrationRequest, HydrationPackage]]:
            reqs = [
                _hydrate_req(_USER_A, "c1"),
                _hydrate_req(_USER_B, "c2"),
                _hydrate_req(_USER_A, "c3"),
                _hydrate_req(_USER_B, "c4"),
            ]
            pkgs = await asyncio.gather(*(manager.hydrate(r) for r in reqs))
            return list(zip(reqs, pkgs))

        pairs = asyncio.run(run())
        rows = []
        for call_idx, (req, pkg) in enumerate(pairs, 1):
            other = _USER_B if req.user_id == _USER_A else _USER_A
            rows.append({**_audit(pkg, req.user_id, other), "call": call_idx})

        _report_table(rows)

        for row in rows:
            assert row["cross_leak"] == 0, (
                f"SECURITY GAP: concurrent call #{row['call']} for {row['user']} "
                f"leaked {row['cross_leak']} record(s): {row['leaked_contents']} -- "
                f"needs-reviewer: cross-user memory bleed under asyncio concurrency"
            )
            assert row["own"] > 0, (
                f"concurrent call #{row['call']} for {row['user']} returned no own records"
            )


class TestSearchCallScoping:
    """Verify that store.search is only ever called with the requesting user's id.

    This catches a class of bugs where the manager passes a stale or wrong
    user_id to store.search rather than the one from the active HydrationRequest.
    """

    def test_user_a_hydrate_only_searches_user_a(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()
        asyncio.run(manager.hydrate(_hydrate_req(_USER_A, "sa")))

        log = list(store_double.search_log)
        print(f"\nSearch log for user A's hydrate: {log}")

        wrong = [(t, u) for t, u in log if u != _USER_A]
        assert not wrong, (
            f"SECURITY GAP: user A's hydrate called store.search with wrong "
            f"user_id(s): {wrong}"
        )
        assert log, "user A's hydrate must call store.search at least once"

    def test_user_b_hydrate_only_searches_user_b(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()
        asyncio.run(manager.hydrate(_hydrate_req(_USER_B, "sb")))

        log = list(store_double.search_log)
        print(f"\nSearch log for user B's hydrate: {log}")

        wrong = [(t, u) for t, u in log if u != _USER_B]
        assert not wrong, (
            f"SECURITY GAP: user B's hydrate called store.search with wrong "
            f"user_id(s): {wrong}"
        )
        assert log, "user B's hydrate must call store.search at least once"

    def test_concurrent_calls_use_correct_user_ids(self, store_double: _StoreDouble) -> None:
        """Under concurrency, store.search is only ever called with a known user_id."""
        manager = MemoryManager()

        async def run() -> None:
            await asyncio.gather(
                manager.hydrate(_hydrate_req(_USER_A, "ca")),
                manager.hydrate(_hydrate_req(_USER_B, "cb")),
            )

        asyncio.run(run())

        log = list(store_double.search_log)
        known = {_USER_A, _USER_B}
        unexpected = [(t, u) for t, u in log if u not in known]
        print(f"\nFull search log (concurrent): {log}")
        assert not unexpected, (
            f"SECURITY GAP: store.search called with unexpected user_id(s): {unexpected}"
        )
        a_calls = [(t, u) for t, u in log if u == _USER_A]
        b_calls = [(t, u) for t, u in log if u == _USER_B]
        assert a_calls, "user A's hydrate must call store.search"
        assert b_calls, "user B's hydrate must call store.search"


class TestFailClosed:
    """Missing / empty user_id must return an empty package without store access.

    §V.20 fail-closed gate: no scope, no memory.  A degraded package would
    imply an infrastructure fault; an empty healthy package is the expected
    signal for a missing scope.  store.search must never be called -- even
    returning another user's data would be a security gap.
    """

    def test_empty_user_id_returns_empty_package(self, store_double: _StoreDouble) -> None:
        manager = MemoryManager()
        calls_before = len(store_double.search_log)

        pkg = asyncio.run(
            manager.hydrate(
                HydrationRequest(
                    session_id="s",
                    user_id="",
                    normalized=_norm("any query"),
                    token_budget=2000,
                )
            )
        )

        empty_row = {
            "user": "(empty user_id)",
            "call": 1,
            "returned": len(pkg.items),
            "own": 0,
            "cross_leak": 0,
            "verdict": "scoped (fail-closed)",
        }
        _report_table([empty_row])

        assert pkg.items == [], (
            "fail-closed: empty user_id must yield an empty items list"
        )
        assert pkg.degraded is False, (
            "fail-closed is a scope gate, not an infrastructure degradation"
        )
        assert pkg.notes is not None, (
            "fail-closed package must carry an explanatory note"
        )
        assert len(store_double.search_log) == calls_before, (
            "SECURITY GAP: store.search must NOT be called when user_id is empty"
        )

    def test_empty_user_id_never_returns_other_users_data(
        self, store_double: _StoreDouble
    ) -> None:
        """Confirm the empty-scope path cannot accidentally return seeded data."""
        manager = MemoryManager()
        pkg = asyncio.run(
            manager.hydrate(
                HydrationRequest(session_id="s", user_id="", normalized=_norm("kiwi mango"), token_budget=2000)
            )
        )
        # The query text overlaps both users' seeded content -- if the scope
        # gate were missing, a worst-case implementation might return all records.
        leaked = [i for i in pkg.items if _USER_A in i.content or _USER_B in i.content]
        assert not leaked, (
            f"SECURITY GAP: empty user_id returned data belonging to another user: "
            f"{[i.content for i in leaked]}"
        )
