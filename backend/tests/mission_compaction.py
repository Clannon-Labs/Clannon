"""
Tests for the Mission Engine's §8 compaction
(core/orchestrator/mission_compaction.py).

Design ref: proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md
§8/§9. `graph_compaction_eligible_tasks` reads BLOCKS/FEEDS dependents
straight from the graph via `edges_of()` (foundation/contracts/graph.py,
landed 45b6ab4) -- unlike the in-session mirror this module used to carry,
eligibility here is correct after a cold restart too, so this is no longer a
separate scenario from tests/mission_operate.py's restart-survival test; it's
the same durability, one layer up.

Two tiers of test, deliberately: `_StubGraphPort` below unit-tests the
DECISION logic (fail-closed on degraded, unresolved dependents, the
all-terminal-required rule) cheaply. It does NOT prove edge direction (src =
the depended-on task, dst = the dependent) -- a stub whose `edges_of()`
replays whatever direction a test assumes would be a circular oracle, proving
nothing. `test_real_graph_manager_...` is what actually proves direction: it
round-trips through `apply_turn()`'s real writes and the real `GraphManager`,
the same convention as tests/mission_operate.py's capstone test.

The discriminating case (the whole point of the frontier check, not just a
smoke test): a terminal task that FEEDS a still-non-terminal task must NOT be
eligible for compaction, and becomes eligible only once that dependent also
goes terminal.

Run:
    cd backend && .venv/bin/python -m pytest tests/mission_compaction.py -v
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from foundation import EdgeLabel, GraphEdge, GraphResult, GraphScope

from core.orchestrator.mission import Criterion, MissionStatus, TaskStatus
from core.orchestrator.mission_operate import MissionState, NewTask, OperateStepTurn, TaskNode, TaskTransition
from core.orchestrator.mission_compaction import (
    MissionWorkingContext,
    compact_working_context,
    graph_compaction_eligible_tasks,
    record_task_detail,
)


def _task(task_id: str, status: TaskStatus | None, summary: str = "") -> TaskNode:
    return TaskNode(task_id=task_id, node_id=f"node#{task_id}", status=status, summary=summary or task_id)


def _state(*tasks: TaskNode) -> MissionState:
    return MissionState(mission_id="m1", intent="intent", criteria=[], status=MissionStatus.ACTIVE, tasks=list(tasks))


def _run(coro):
    return asyncio.run(coro)


# ─── _StubGraphPort: decision-logic only, direction NOT asserted here ──────

@dataclass
class _StubGraphPort:
    """See module docstring: proves the eligibility DECISION, not direction."""
    edges: dict[EdgeLabel, list[GraphEdge]] = field(default_factory=dict)
    degraded_labels: frozenset = frozenset()

    async def edges_of(self, scope: GraphScope, node_id: str, label: EdgeLabel) -> GraphResult:
        if label in self.degraded_labels:
            return GraphResult(degraded=True, notes="stub: forced degraded")
        incident = [e for e in self.edges.get(label, []) if e.src_id == node_id or e.dst_id == node_id]
        return GraphResult(edges=incident)


_SCOPE = GraphScope(user_id="u1")


# ─── the discriminating case: partial frontier ─────────────────────────────

def test_terminal_task_with_nonterminal_dependent_is_not_eligible():
    state = _state(_task("t1", TaskStatus.DONE), _task("t2", None))  # t2 still active
    graph = _StubGraphPort(edges={EdgeLabel.FEEDS: [GraphEdge(src_id="node#t1", dst_id="node#t2", label=EdgeLabel.FEEDS)]})
    eligible = _run(graph_compaction_eligible_tasks(graph, _SCOPE, state))
    assert "t1" not in eligible, "t1 still feeds a non-terminal t2 -- must stay on the frontier"


def test_becomes_eligible_once_its_dependent_also_goes_terminal():
    state = _state(_task("t1", TaskStatus.DONE), _task("t2", TaskStatus.DONE))
    graph = _StubGraphPort(edges={EdgeLabel.FEEDS: [GraphEdge(src_id="node#t1", dst_id="node#t2", label=EdgeLabel.FEEDS)]})
    eligible = _run(graph_compaction_eligible_tasks(graph, _SCOPE, state))
    assert eligible == frozenset({"t1", "t2"}), "both now terminal: t1 (dependent done), t2 (no dependents)"


def test_nonterminal_task_is_never_eligible_regardless_of_dependents():
    state = _state(_task("t1", None))
    graph = _StubGraphPort()
    assert _run(graph_compaction_eligible_tasks(graph, _SCOPE, state)) == frozenset()


def test_terminal_task_with_no_recorded_dependents_is_eligible():
    state = _state(_task("t1", TaskStatus.DONE))
    graph = _StubGraphPort()
    assert _run(graph_compaction_eligible_tasks(graph, _SCOPE, state)) == frozenset({"t1"})


def test_unknown_dependent_fails_closed_never_eligible_on_ambiguous_info():
    state = _state(_task("t1", TaskStatus.DONE))
    graph = _StubGraphPort(edges={
        EdgeLabel.FEEDS: [GraphEdge(src_id="node#t1", dst_id="ghost-not-in-state", label=EdgeLabel.FEEDS)],
    })
    assert _run(graph_compaction_eligible_tasks(graph, _SCOPE, state)) == frozenset(), \
        "an unresolvable dependent must never be silently treated as terminal"


def test_degraded_edges_of_read_returns_none_never_a_partial_set():
    state = _state(_task("t1", TaskStatus.DONE))
    graph = _StubGraphPort(degraded_labels=frozenset({EdgeLabel.BLOCKS}))
    result = _run(graph_compaction_eligible_tasks(graph, _SCOPE, state))
    assert result is None, "a degraded graph read must skip the whole pass, not silently compact"


# ─── capstone: the real GraphManager proves edge direction ─────────────────

def test_real_graph_manager_round_trips_frontier_across_a_restart():
    """apply_turn always writes GraphEdge(src_id=<depended-on task>,
    dst_id=<the new/dependent task>) -- this proves graph_compaction_eligible_
    tasks reads that back correctly (not inverted) against the real store,
    the same convention as tests/mission_operate.py's capstone test."""
    from core.memory.graph_manager import GraphManager
    from core.orchestrator.mission_operate import apply_turn, create_mission, read_mission_state

    async def go():
        manager = GraphManager()
        scope = GraphScope(user_id="real-compaction-u1")
        await create_mission(manager, scope, "m1", "intent", [Criterion(description="c1")])
        await apply_turn(manager, scope, "m1", OperateStepTurn(new_tasks=(NewTask(task_id="t1", summary="first"),)))
        await apply_turn(manager, scope, "m1", OperateStepTurn(
            new_tasks=(NewTask(task_id="t2", summary="second", feeds=("t1",)),),
        ))
        await apply_turn(manager, scope, "m1", OperateStepTurn(
            transitions=(TaskTransition(task_id="t1", status=TaskStatus.DONE, summary="t1 done"),),
        ))

        state = await read_mission_state(manager, scope, "m1")
        eligible = await graph_compaction_eligible_tasks(manager, scope, state)
        assert eligible == frozenset(), "t1 is terminal but t2 (still active) feeds off it -- not eligible yet"

        await apply_turn(manager, scope, "m1", OperateStepTurn(
            transitions=(TaskTransition(task_id="t2", status=TaskStatus.DONE, summary="t2 done"),),
        ))
        state_after = await read_mission_state(manager, scope, "m1")
        eligible_after = await graph_compaction_eligible_tasks(manager, scope, state_after)
        assert eligible_after == frozenset({"t1", "t2"}), "both terminal now: t1 (dependent done), t2 (no dependents)"

    asyncio.run(go())


# ─── compact_working_context: digest applied only to eligible tasks ───────

def test_compact_working_context_digests_only_eligible_tasks_leaves_rest_full():
    working = MissionWorkingContext()
    working = record_task_detail(working, "t1", "a very long verbose account of what t1 actually did")
    working = record_task_detail(working, "t2", "t2's in-progress notes")

    compacted = compact_working_context(working, frozenset({"t1"}), digest=lambda tid, detail: f"[digest:{tid}]")
    assert compacted.full_detail["t1"] == "[digest:t1]"
    assert compacted.full_detail["t2"] == "t2's in-progress notes", "t2 not in the eligible set -- must stay full"


def test_compact_working_context_is_pure_never_mutates_its_input():
    working = record_task_detail(MissionWorkingContext(), "t1", "full detail")
    compact_working_context(working, frozenset({"t1"}), digest=lambda tid, detail: "shrunk")
    assert working.full_detail["t1"] == "full detail", "the original MissionWorkingContext must be untouched"
