"""
Mission Engine graph substrate — `core/memory/mission_graph_store.py` (typed
Mission/Task nodes + Blocks/Feeds/Supersedes edges over Kuzu) and
`GraphManager`'s dispatch extension (`write()` now also accepts MISSION/TASK
nodes + the three new edge labels; the new `members()` bulk-read method).

Ratified 2026-07-05 from the memory specialist's empirically-verified answers
to orchestration's two GraphPort-semantics questions
(`proposals/archive/to-backend/2026-07-05_graphport-semantics-answers.md`):
  Q1 — a repeat write to the same node id mutates properties IN PLACE
       (Kuzu `MERGE...ON MATCH SET`), no transition history kept (status is a
       mutable cursor; SUPERSEDES carries re-plan history, a different thing).
  Q2 — `lookup(label=X)` alone is NOT a bulk read (proven empty-by-
       construction elsewhere); `members()` is the new bulk-read method,
       filtering `mission_id` as a node PROPERTY (not a GraphScope dimension).

Every test runs against a REAL embedded Kuzu db (fresh tmp_path per test via
`tests/conftest.py`'s autouse `_fresh_graph_store` fixture, shared with
`memory_graph_manager.py`/`memory_graph_store.py` rather than duplicated) —
no mocks for the happy paths, same convention as the existing graph tests.
Async methods driven via `asyncio.run()` inside plain `def` tests (no
pytest-asyncio wired in — see `memory_graph_manager.py`'s own note).

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_mission_graph.py -v
"""
from __future__ import annotations

import asyncio

import pytest

import core.memory.graph_store as graph_store
import core.memory.mission_graph_store as mission_graph_store
from core.memory.graph_manager import GraphManager
from foundation import EdgeLabel, EdgeOrigin, GraphEdge, GraphNode, GraphPort, GraphScope, NodeLabel


def _mission_row(scope: GraphScope, mission_id: str, **overrides) -> dict:
    row = {
        "id": graph_store.node_id(scope, mission_id), "user_id": scope.user_id,
        "repo_id": scope.repo_id, "mission_id": mission_id, "intent": "ship it",
        "success_criteria": ["a", "b"], "status": "active", "updated_at": 1.0,
    }
    row.update(overrides)
    return row


def _task_row(scope: GraphScope, task_id: str, mission_id: str, **overrides) -> dict:
    row = {
        "id": graph_store.node_id(scope, task_id), "user_id": scope.user_id,
        "repo_id": scope.repo_id, "task_id": task_id, "mission_id": mission_id,
        "summary": f"do {task_id}", "status": "active", "evidence": "", "updated_at": 1.0,
    }
    row.update(overrides)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# mission_graph_store.py — low-level Kuzu mechanics
# ─────────────────────────────────────────────────────────────────────────────

def test_mission_upsert_then_read_back():
    scope = GraphScope(user_id="u1")
    applied = mission_graph_store.upsert_typed_nodes("mission", [_mission_row(scope, "m1")])
    assert applied == [graph_store.node_id(scope, "m1")]
    result = mission_graph_store.typed_members("mission", scope)
    assert len(result.rows) == 1
    assert result.rows[0]["mission_id"] == "m1"
    assert result.rows[0]["success_criteria"] == ["a", "b"]


def test_q1_repeat_write_mutates_status_in_place_no_duplicate():
    """The load-bearing Q1 proof, at the mission_graph_store level: two writes
    to the SAME task id with different status values leave exactly one node,
    holding the LATEST status — not two nodes, not the original value."""
    scope = GraphScope(user_id="u1")
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t1", "m1", status="active")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t1", "m1", status="blocked")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t1", "m1", status="done")])
    result = mission_graph_store.typed_members("task", scope, parent_id="m1")
    assert len(result.rows) == 1, "a repeat write to the same id must not duplicate the node"
    assert result.rows[0]["status"] == "done", "must hold the LATEST write, not the first"


def test_create_only_fields_are_immune_to_a_repeat_write():
    """A MISSION's intent/success_criteria are write-once (NodeLabel's own
    docstring) — a repeat write with a DIFFERENT intent must not change it,
    only the mutable status/updated_at cursor may move."""
    scope = GraphScope(user_id="u1")
    mission_graph_store.upsert_typed_nodes("mission", [_mission_row(scope, "m1", intent="original intent")])
    mission_graph_store.upsert_typed_nodes(
        "mission", [_mission_row(scope, "m1", intent="a DIFFERENT intent", status="blocked")]
    )
    result = mission_graph_store.typed_members("mission", scope)
    assert len(result.rows) == 1
    assert result.rows[0]["intent"] == "original intent", "create_only field must not mutate on repeat write"
    assert result.rows[0]["status"] == "blocked", "mutable field must still refresh"


def test_members_parent_id_filters_to_one_mission():
    scope = GraphScope(user_id="u1")
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t1", "m1")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t2", "m1")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t3", "m2")])
    m1_tasks = mission_graph_store.typed_members("task", scope, parent_id="m1")
    assert {r["task_id"] for r in m1_tasks.rows} == {"t1", "t2"}
    m2_tasks = mission_graph_store.typed_members("task", scope, parent_id="m2")
    assert {r["task_id"] for r in m2_tasks.rows} == {"t3"}


def test_tenant_isolation_same_mission_and_task_id_different_user():
    """Q2's ruling: mission_id is a filter WITHIN user_id, never a tenant
    boundary on its own — an adversarial or coincidental id collision across
    users must never cross-leak."""
    scope_a = GraphScope(user_id="u1")
    scope_b = GraphScope(user_id="u2")
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope_a, "t1", "m1", summary="user A's task")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope_b, "t1", "m1", summary="user B's task")])
    a_view = mission_graph_store.typed_members("task", scope_a, parent_id="m1")
    b_view = mission_graph_store.typed_members("task", scope_b, parent_id="m1")
    assert len(a_view.rows) == 1 and a_view.rows[0]["summary"] == "user A's task"
    assert len(b_view.rows) == 1 and b_view.rows[0]["summary"] == "user B's task"


def test_unknown_kind_returns_empty_not_an_exception():
    scope = GraphScope(user_id="u1")
    assert mission_graph_store.upsert_typed_nodes("not-a-real-kind", [{"id": "x"}]) == []
    result = mission_graph_store.typed_members("not-a-real-kind", scope)
    assert result.degraded is True
    assert result.rows == ()


def test_blocks_edge_upsert_and_asserted_wins_protection():
    scope = GraphScope(user_id="u1")
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t1", "m1")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t2", "m1")])
    src, dst = graph_store.node_id(scope, "t1"), graph_store.node_id(scope, "t2")
    applied = mission_graph_store.upsert_typed_edges("blocks", [{"src": src, "dst": dst, "origin": "asserted"}])
    assert applied == [{"src": src, "dst": dst, "origin": "asserted"}]
    # a later INFERRED write must not overwrite an ASSERTED edge
    reapplied = mission_graph_store.upsert_typed_edges("blocks", [{"src": src, "dst": dst, "origin": "inferred"}])
    assert reapplied == [], "an asserted edge must be protected from a later inferred overwrite"


def test_feeds_and_supersedes_are_independent_edge_tables():
    scope = GraphScope(user_id="u1")
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t1", "m1")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(scope, "t2", "m1")])
    src, dst = graph_store.node_id(scope, "t1"), graph_store.node_id(scope, "t2")
    feeds = mission_graph_store.upsert_typed_edges("feeds", [{"src": src, "dst": dst, "origin": "inferred"}])
    supersedes = mission_graph_store.upsert_typed_edges("supersedes", [{"src": src, "dst": dst, "origin": "inferred"}])
    assert len(feeds) == 1 and len(supersedes) == 1, "both edge kinds apply independently between the same pair"


def test_degrade_never_fail_when_store_disabled(monkeypatch):
    monkeypatch.setattr(graph_store, "DISABLED", True)
    scope = GraphScope(user_id="u1")
    assert mission_graph_store.upsert_typed_nodes("mission", [_mission_row(scope, "m1")]) == []
    result = mission_graph_store.typed_members("mission", scope)
    assert result.degraded is True


def test_delete_user_purges_mission_and_task_nodes_for_that_user_only():
    """The Mission Engine half of right-to-erasure — previously nothing
    purged Mission/Task data on account deletion at all."""
    owner, other = GraphScope(user_id="owner"), GraphScope(user_id="other")
    mission_graph_store.upsert_typed_nodes("mission", [_mission_row(owner, "m1")])
    mission_graph_store.upsert_typed_nodes("task", [_task_row(owner, "t1", "m1")])
    mission_graph_store.upsert_typed_nodes("mission", [_mission_row(other, "m1")])

    mission_graph_store.delete_user("owner")

    assert mission_graph_store.typed_members("mission", owner).rows == ()
    assert mission_graph_store.typed_members("task", owner, parent_id="m1").rows == ()
    # the other tenant's identically-keyed mission is untouched
    assert len(mission_graph_store.typed_members("mission", other).rows) == 1


def test_delete_user_is_a_noop_on_missing_user_id():
    scope = GraphScope(user_id="owner")
    mission_graph_store.upsert_typed_nodes("mission", [_mission_row(scope, "m1")])

    mission_graph_store.delete_user("")  # must not raise, must not touch anything

    assert len(mission_graph_store.typed_members("mission", scope).rows) == 1


# ─────────────────────────────────────────────────────────────────────────────
# GraphManager — through the port (write() dispatch + members())
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def manager() -> GraphManager:
    return GraphManager()


def test_graph_manager_still_satisfies_graphport_after_members_added(manager):
    """The exact ordering concern the backend-agent flagged: adding members()
    to GraphManager BEFORE the Protocol gains it must keep isinstance green
    (GraphManager becomes a superset, never a mismatch)."""
    assert isinstance(manager, GraphPort)


def test_write_accepts_mission_and_task_nodes_through_the_port(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        mission = GraphNode(
            node_id=graph_store.node_id(scope, "m1"), label=NodeLabel.MISSION, scope=scope,
            properties={"mission_id": "m1", "intent": "ship it", "success_criteria": ["a"],
                        "status": "active", "updated_at": 1.0},
        )
        task = GraphNode(
            node_id=graph_store.node_id(scope, "t1"), label=NodeLabel.TASK, scope=scope,
            properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        result = await manager.write(scope, [mission, task], [])
        assert result.degraded is False
        assert {n.node_id for n in result.nodes} == {mission.node_id, task.node_id}
        assert result.notes == ""
    asyncio.run(go())


def test_write_accepts_mission_engine_edges_through_the_port(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        t1 = GraphNode(node_id=graph_store.node_id(scope, "t1"), label=NodeLabel.TASK, scope=scope,
                        properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                                    "evidence": "", "updated_at": 1.0})
        t2 = GraphNode(node_id=graph_store.node_id(scope, "t2"), label=NodeLabel.TASK, scope=scope,
                        properties={"task_id": "t2", "mission_id": "m1", "summary": "s", "status": "active",
                                    "evidence": "", "updated_at": 1.0})
        await manager.write(scope, [t1, t2], [])
        for label in (EdgeLabel.BLOCKS, EdgeLabel.FEEDS, EdgeLabel.SUPERSEDES):
            result = await manager.write(
                scope, [], [GraphEdge(src_id=t1.node_id, dst_id=t2.node_id, label=label, origin=EdgeOrigin.INFERRED)]
            )
            assert len(result.edges) == 1, f"{label.value} edge should apply"
            assert result.edges[0].label == label
    asyncio.run(go())


def test_members_through_the_port_returns_typed_graphnodes(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        for tid in ("t1", "t2"):
            await manager.write(scope, [GraphNode(
                node_id=graph_store.node_id(scope, tid), label=NodeLabel.TASK, scope=scope,
                properties={"task_id": tid, "mission_id": "m1", "summary": f"do {tid}", "status": "active",
                            "evidence": "", "updated_at": 1.0},
            )], [])
        result = await manager.members(scope, NodeLabel.TASK, parent_id="m1")
        assert len(result.nodes) == 2
        assert all(n.label == NodeLabel.TASK for n in result.nodes)
        assert all(n.scope == scope for n in result.nodes)
        ids = {n.properties["task_id"] for n in result.nodes}
        assert ids == {"t1", "t2"}
    asyncio.run(go())


def test_members_fail_closed_on_missing_user_id(manager):
    async def go():
        result = await manager.members(GraphScope(user_id=""), NodeLabel.TASK, parent_id="m1")
        assert result.degraded is True
    asyncio.run(go())


def test_members_degrades_on_store_down(manager, monkeypatch):
    async def go():
        monkeypatch.setattr(graph_store, "DISABLED", True)
        result = await manager.members(GraphScope(user_id="u1"), NodeLabel.TASK, parent_id="m1")
        assert result.degraded is True
    asyncio.run(go())


def test_members_on_an_unbacked_label_is_empty_not_an_error(manager):
    async def go():
        result = await manager.members(GraphScope(user_id="u1"), NodeLabel.ENTITY, parent_id="")
        assert result.degraded is False
        assert result.nodes == []
        assert "not" in result.notes or "no bulk" in result.notes
    asyncio.run(go())


def test_write_still_rejects_a_codefile_node_missing_path(manager):
    """The pre-existing CODE_FILE path must be completely unaffected by the
    new dispatch branches."""
    async def go():
        scope = GraphScope(user_id="u1")
        bad = GraphNode(node_id="whatever", label=NodeLabel.CODE_FILE, scope=scope, properties={})
        result = await manager.write(scope, [bad], [])
        assert result.nodes == []
        assert "path" in result.notes
    asyncio.run(go())


def test_write_rejects_caller_supplied_id_and_user_id_in_properties(manager):
    """A malicious/buggy properties dict naming id/user_id/repo_id must never
    override the manager-computed row identity — the fix behind Q2's generic
    marshalling: `{**properties, "id": ..., "user_id": ..., "repo_id": ...}`,
    spread FIRST so the authoritative keys always win."""
    async def go():
        scope = GraphScope(user_id="u1")
        real_id = graph_store.node_id(scope, "t1")
        evil = GraphNode(
            node_id=real_id, label=NodeLabel.TASK, scope=scope,
            properties={"task_id": "t1", "mission_id": "m1", "id": "HACKED", "user_id": "attacker",
                        "repo_id": "attacker-repo", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        result = await manager.write(scope, [evil], [])
        assert real_id in {n.node_id for n in result.nodes}

        members = await manager.members(scope, NodeLabel.TASK, parent_id="m1")
        t1 = next(n for n in members.nodes if n.properties.get("task_id") == "t1")
        assert t1.node_id == real_id

        attacker_scope = GraphScope(user_id="attacker")
        attacker_view = await manager.members(attacker_scope, NodeLabel.TASK, parent_id="m1")
        assert attacker_view.nodes == [], "the malicious user_id property must not have created a real row"
    asyncio.run(go())


def test_mixed_write_codefile_and_mission_engine_nodes_together(manager, tmp_path):
    """CodeFile and Mission/Task nodes can be written in the SAME write() call
    without interfering with each other — the two dispatch paths coexist."""
    async def go():
        scope = GraphScope(user_id="u1")
        code_node = GraphNode(
            node_id=graph_store.node_id(scope, "a.py"), label=NodeLabel.CODE_FILE, scope=scope,
            properties={"path": "a.py"},
        )
        task_node = GraphNode(
            node_id=graph_store.node_id(scope, "t1"), label=NodeLabel.TASK, scope=scope,
            properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        result = await manager.write(scope, [code_node, task_node], [])
        assert {n.node_id for n in result.nodes} == {code_node.node_id, task_node.node_id}
    asyncio.run(go())


def test_graph_manager_delete_user_purges_codefile_and_mission_task_together(manager):
    """GraphManager.delete_user (not on GraphPort — a delivery-layer surface,
    same shape as MemoryManager.delete_user) must clear BOTH the CodeFile
    tier and the Mission/Task tier for the target user, and leave another
    tenant's identically-shaped data alone."""
    async def go():
        owner, other = GraphScope(user_id="owner"), GraphScope(user_id="other")
        code_node = GraphNode(
            node_id=graph_store.node_id(owner, "a.py"), label=NodeLabel.CODE_FILE, scope=owner,
            properties={"path": "a.py"},
        )
        task_node = GraphNode(
            node_id=graph_store.node_id(owner, "t1"), label=NodeLabel.TASK, scope=owner,
            properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        other_task = GraphNode(
            node_id=graph_store.node_id(other, "t1"), label=NodeLabel.TASK, scope=other,
            properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        await manager.write(owner, [code_node, task_node], [])
        await manager.write(other, [other_task], [])

        await manager.delete_user("owner")

        assert (await manager.lookup(owner, natural_key="a.py")).nodes == []
        assert (await manager.members(owner, NodeLabel.TASK, parent_id="m1")).nodes == []
        other_view = await manager.members(other, NodeLabel.TASK, parent_id="m1")
        assert len(other_view.nodes) == 1, "another tenant's data must survive delete_user"
    asyncio.run(go())
