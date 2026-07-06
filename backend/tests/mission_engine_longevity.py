"""
Mission Engine — the §9 long-horizon capstone, combined.

Design ref: proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md §9;
ratified with a strengthening: proposals/archive/to-backend/
2026-07-06_b1-step1-mission-engine-verification-design.md.

tests/mission_operate.py and tests/mission_compaction.py each prove their own
slice of §9 in isolation: restart survival, compaction eligibility, the
completion gate, the budget pre-check. None of them prove the actual
long-horizon CLAIM — that the SAME mission, compacted repeatedly and then
restarted, stays byte-for-byte anchored to its original intent, with its task
graph structure untouched, right up to the moment it concludes or pauses. This
file proves that combined claim, hermetically, in milliseconds.

"Week-long, many times over" (the brief's B2 wording) is represented as THREE
compaction rounds (N>=3 per the 2026-07-06 ruling) with the continuity
invariant re-asserted after EVERY round — not just checked once at the end.
This proves the property holds across multiple rounds, not merely "more than
once": a regression that only appears on round 3 would be caught here, same
compression convention tests/benchmarks/e2_project_continuity.py already uses
for "weeks later" (a handful of distinct milestones standing in for elapsed
time, not a real clock). The three rounds are narratively distinct (each
advances a different task to terminal, shifting which tasks are compaction-
eligible), not a uniform repeat — see `_seed_and_survive_rounds` below.

Reuses tests/mission_operate.py's FakeGraphPort rather than inventing a third
test double — _LongevityGraphPort below adds the one method
(`edges_of`) that module's own tests never needed, built from the edge list
FakeGraphPort already tracks.

Run:
    cd backend && .venv/bin/python -m pytest tests/mission_engine_longevity.py -v
"""

from __future__ import annotations

import asyncio

from foundation import EdgeLabel, GraphEdge, GraphResult, TokenBudget

from mission_operate import FakeBudgetPort, FakeGraphPort, _BSCOPE, _PLENTY, _SCOPE
from core.orchestrator.mission import Criterion, CompletionJudgment, CriterionVerdict, MissionStatus, TaskStatus
from core.orchestrator.mission_operate import (
    NewTask,
    OperateStepTurn,
    TaskTransition,
    apply_turn,
    create_mission,
    read_mission_state,
    run_operate_step,
    write_mission_status,
)
from core.orchestrator.mission_compaction import (
    MissionWorkingContext,
    compact_working_context,
    graph_compaction_eligible_tasks,
    record_task_detail,
)

_INTENT = "ship the quarterly report"
_CRITERIA_DESCRIPTIONS = ["data verified", "narrative reviewed"]


def _run(coro):
    return asyncio.run(coro)


class _LongevityGraphPort(FakeGraphPort):
    """FakeGraphPort plus edges_of() -- the one method mission_compaction.py
    needs that mission_operate.py's own tests never exercise. Built from the
    edge list FakeGraphPort already tracks in self._edges; no new state."""

    async def edges_of(self, scope, node_id, label):
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id -- refused, fail-closed")
        incident = [
            GraphEdge(src_id=e["src"], dst_id=e["dst"], label=e["label"])
            for e in self._edges if e["label"] == label and node_id in (e["src"], e["dst"])
        ]
        return GraphResult(edges=incident)


def _assert_anchor_unchanged(state) -> None:
    """The drift-proof claim, literally checked: intent/criteria never move,
    no matter how many compaction rounds or restarts have happened."""
    assert state.intent == _INTENT
    assert [c.description for c in state.criteria] == _CRITERIA_DESCRIPTIONS


async def _seed() -> _LongevityGraphPort:
    """Seeds one mission exercising every §1/§5 shape the combined scenario
    needs: a supersede (t3 supersedes t1) and a FEEDS dependency (t3 feeds
    t2) whose terminal status shifts across rounds -- the discriminating case
    mission_compaction.py's own tests call out, not just a smoke shape."""
    graph = _LongevityGraphPort()
    criteria = [Criterion(description=d) for d in _CRITERIA_DESCRIPTIONS]
    await create_mission(graph, _SCOPE, "m1", _INTENT, criteria)
    await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
        new_tasks=(NewTask(task_id="t1", summary="v1"),),
    ))
    await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
        transitions=(TaskTransition(task_id="t1", status=TaskStatus.DONE, summary="t1 done"),),
    ))
    await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(new_tasks=(
        NewTask(task_id="t3", summary="v2 replaces v1", supersedes="t1"),
        NewTask(task_id="t2", summary="reviews t3's output", feeds=("t3",)),
    )))
    return graph


async def _round(graph, working: MissionWorkingContext) -> MissionWorkingContext:
    """One compaction round: read state, assert the anchor, record this
    round's verbose detail, compact eligible tasks, then re-read and assert
    the anchor AND the task graph's structure/status are untouched -- §8's
    promise that compaction only ever moves detail, never graph structure."""
    state = await read_mission_state(graph, _SCOPE, "m1")
    _assert_anchor_unchanged(state)
    for t in state.tasks:
        working = record_task_detail(working, t.task_id, f"verbose findings for {t.task_id}")

    eligible = await graph_compaction_eligible_tasks(graph, _SCOPE, state)
    assert eligible is not None, "a hermetic fake must never degrade"
    working = compact_working_context(working, eligible, digest=lambda tid, detail: f"[digest:{tid}]")
    for task_id in eligible:
        assert working.full_detail[task_id] == f"[digest:{task_id}]"
    for task_id, detail in working.full_detail.items():
        if task_id not in eligible:
            assert not detail.startswith("[digest:"), "compaction must never touch an ineligible task's detail"

    reread = await read_mission_state(graph, _SCOPE, "m1")
    _assert_anchor_unchanged(reread)
    assert {t.task_id: t.status for t in reread.tasks} == {t.task_id: t.status for t in state.tasks}, (
        "compaction acts on working-context detail only -- the graph's structure/status must never move"
    )
    return working


async def _seed_and_survive_rounds() -> _LongevityGraphPort:
    """Seeds the mission, then advances t3/t2 to terminal while running a
    compaction round after each step -- the shared "already lived through N
    rounds" starting point every test in this file continues from, so the
    completion-gate and budget-pre-check proofs run against the SAME
    longevity-shaped mission, not a bare fresh one."""
    graph = await _seed()
    working = MissionWorkingContext()

    # Round 1: only t1 is terminal (DONE, no BLOCKS/FEEDS dependents recorded
    # -- the SUPERSEDES edge doesn't count) -- eligible immediately.
    working = await _round(graph, working)
    state = await read_mission_state(graph, _SCOPE, "m1")
    eligible = await graph_compaction_eligible_tasks(graph, _SCOPE, state)
    assert eligible == frozenset({"t1"})

    # Round 2: t3 goes DONE, but it FEEDS t2 (still active) -- the
    # discriminating case: t3 must NOT be eligible yet despite being terminal.
    await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
        transitions=(TaskTransition(task_id="t3", status=TaskStatus.DONE, summary="t3 done"),),
    ))
    working = await _round(graph, working)
    state = await read_mission_state(graph, _SCOPE, "m1")
    eligible = await graph_compaction_eligible_tasks(graph, _SCOPE, state)
    assert eligible == frozenset({"t1"}), "t3 still feeds a non-terminal t2 -- must stay on the frontier"

    # Round 3: t2 goes DONE -- now t3's dependent is terminal too, so both
    # t3 and t2 join t1 as eligible.
    await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
        transitions=(TaskTransition(task_id="t2", status=TaskStatus.DONE, summary="t2 done"),),
    ))
    working = await _round(graph, working)
    state = await read_mission_state(graph, _SCOPE, "m1")
    eligible = await graph_compaction_eligible_tasks(graph, _SCOPE, state)
    assert eligible == frozenset({"t1", "t2", "t3"})

    return graph


# ─── §9 steps 1-3, combined: seed, N compaction rounds, a full restart ─────

def test_mission_survives_many_compaction_rounds_then_a_full_restart():
    async def restart_and_verify(graph):
        # No Python state carried over except the durable-store handle itself --
        # every local below is rebuilt fresh, exactly as a new process would.
        state = await read_mission_state(graph, _SCOPE, "m1")
        _assert_anchor_unchanged(state)
        t1, t2, t3 = state.task_by_id("t1"), state.task_by_id("t2"), state.task_by_id("t3")
        assert t1 is not None, "the superseded task must still be present, never deleted"
        assert t1.status == TaskStatus.DONE and t2.status == TaskStatus.DONE and t3.status == TaskStatus.DONE
        supersede_edges = [e for e in graph._edges if e["label"] == EdgeLabel.SUPERSEDES]
        assert len(supersede_edges) == 1
        assert supersede_edges[0]["src"] == t3.node_id and supersede_edges[0]["dst"] == t1.node_id

    graph = _run(_seed_and_survive_rounds())
    _run(restart_and_verify(graph))


# ─── §9 step 4: completion gate, on a mission that already survived the above ──

def test_completion_gate_holds_then_concludes_on_a_longevity_survived_mission():
    async def go():
        graph = await _seed_and_survive_rounds()
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.all_tasks_terminal(), "the gate below only means something if every task is genuinely terminal"
        await write_mission_status(graph, _SCOPE, "m1", state, MissionStatus.PROPOSED_COMPLETE)

        budget = FakeBudgetPort(_PLENTY)
        unmet = CompletionJudgment(criteria_verdicts=[
            CriterionVerdict(description=_CRITERIA_DESCRIPTIONS[0], met=True, evidence="ok"),
            CriterionVerdict(description=_CRITERIA_DESCRIPTIONS[1], met=False, evidence="not yet"),
        ])
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10,
                                         turn=OperateStepTurn(completion_judgment=unmet))
        assert result.status == MissionStatus.PROPOSED_COMPLETE, "fail-closed: must hold, never auto-DONE"
        held = await read_mission_state(graph, _SCOPE, "m1")
        _assert_anchor_unchanged(held)

        met = CompletionJudgment(criteria_verdicts=[
            CriterionVerdict(description=_CRITERIA_DESCRIPTIONS[0], met=True, evidence="ok"),
            CriterionVerdict(description=_CRITERIA_DESCRIPTIONS[1], met=True, evidence="reviewed"),
        ])
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10,
                                         turn=OperateStepTurn(completion_judgment=met))
        assert result.status == MissionStatus.DONE
        final = await read_mission_state(graph, _SCOPE, "m1")
        assert final.status == MissionStatus.DONE
        _assert_anchor_unchanged(final)
    _run(go())


# ─── §9 step 5: budget pre-check, on a fresh mission (a concluded one is a no-op) ──

def test_budget_pause_blocks_before_any_write_on_a_longevity_shaped_mission():
    async def go():
        graph = await _seed_and_survive_rounds()
        budget = FakeBudgetPort(TokenBudget(user_remaining=10, mission_remaining=10))
        turn = OperateStepTurn(new_tasks=(NewTask(task_id="t4", summary="should never land"),))
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=1_000, turn=turn)
        assert result.status == MissionStatus.BUDGET_PAUSED

        state = await read_mission_state(graph, _SCOPE, "m1")
        _assert_anchor_unchanged(state)
        assert state.task_by_id("t4") is None, "budget pause must short-circuit BEFORE any task content is applied"
        assert state.status == MissionStatus.BUDGET_PAUSED
    _run(go())
