"""
Tests for the Mission Engine's §8 compaction
(core/orchestrator/mission_compaction.py).

Design ref: proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md
§8/§9. This is deliberately a SEPARATE scenario from
tests/mission_operate.py's hermetic restart-survival test (§9 steps 1+3) --
per an advisor review, the two must not be conflated into one "frontier-aware
compaction survives restart" claim. Compaction's `dependents` mirror is
in-session only (see mission_compaction.py's module docstring for exactly
why: GraphPort has no TASK-edge read path today); these tests prove the
in-session decision is correct, not that it survives a cold restart.

The discriminating case (the whole point of the frontier check, not just a
smoke test): a terminal task that FEEDS a still-non-terminal task must NOT be
eligible for compaction, and becomes eligible only once that dependent also
goes terminal.

Run:
    cd backend && .venv/bin/python -m pytest tests/mission_compaction.py -v
"""

from __future__ import annotations

from core.orchestrator.mission_operate import MissionState, NewTask, OperateStepTurn, TaskNode
from core.orchestrator.mission import MissionStatus, TaskStatus
from core.orchestrator.mission_compaction import (
    MissionWorkingContext,
    compact_working_context,
    compaction_eligible_tasks,
    record_task_detail,
    record_turn_dependencies,
)


def _task(task_id: str, status: TaskStatus | None, summary: str = "") -> TaskNode:
    return TaskNode(task_id=task_id, node_id=f"node#{task_id}", status=status, summary=summary or task_id)


def _state(*tasks: TaskNode) -> MissionState:
    return MissionState(mission_id="m1", intent="intent", criteria=[], status=MissionStatus.ACTIVE, tasks=list(tasks))


# ─── record_turn_dependencies: derived purely from NewTask.blocks/feeds ───

def test_record_turn_dependencies_tracks_blocks_and_feeds():
    working = MissionWorkingContext()
    turn = OperateStepTurn(new_tasks=(
        NewTask(task_id="t2", summary="second", blocks=("t1",)),
        NewTask(task_id="t3", summary="third", feeds=("t1",)),
    ))
    updated = record_turn_dependencies(working, turn)
    assert updated.dependents["t1"] == frozenset({"t2", "t3"})
    assert working.dependents == {}, "must be pure -- the original is never mutated"


# ─── the discriminating case: partial frontier ─────────────────────────────

def test_terminal_task_with_nonterminal_dependent_is_not_eligible():
    state = _state(_task("t1", TaskStatus.DONE), _task("t2", None))  # t2 still active
    working = record_turn_dependencies(
        MissionWorkingContext(), OperateStepTurn(new_tasks=(NewTask(task_id="t2", summary="s", blocks=("t1",)),)),
    )
    eligible = compaction_eligible_tasks(state, working)
    assert "t1" not in eligible, "t1 still feeds a non-terminal t2 -- must stay on the frontier"


def test_becomes_eligible_once_its_dependent_also_goes_terminal():
    state = _state(_task("t1", TaskStatus.DONE), _task("t2", TaskStatus.DONE))
    working = record_turn_dependencies(
        MissionWorkingContext(), OperateStepTurn(new_tasks=(NewTask(task_id="t2", summary="s", blocks=("t1",)),)),
    )
    eligible = compaction_eligible_tasks(state, working)
    assert eligible == frozenset({"t1", "t2"}), "both now terminal: t1 (dependent done), t2 (no dependents)"


def test_nonterminal_task_is_never_eligible_regardless_of_dependents():
    state = _state(_task("t1", None))
    working = MissionWorkingContext()
    assert compaction_eligible_tasks(state, working) == frozenset()


def test_terminal_task_with_no_recorded_dependents_is_eligible():
    state = _state(_task("t1", TaskStatus.DONE))
    working = MissionWorkingContext()
    assert compaction_eligible_tasks(state, working) == frozenset({"t1"})


def test_unknown_dependent_fails_closed_never_eligible_on_ambiguous_info():
    state = _state(_task("t1", TaskStatus.DONE))
    working = MissionWorkingContext(dependents={"t1": frozenset({"ghost-task-not-in-state"})})
    assert compaction_eligible_tasks(state, working) == frozenset(), \
        "an unresolvable dependent must never be silently treated as terminal"


# ─── compact_working_context: digest applied only to eligible tasks ───────

def test_compact_working_context_digests_only_eligible_tasks_leaves_rest_full():
    state = _state(_task("t1", TaskStatus.DONE), _task("t2", None))  # t2 still active
    working = record_turn_dependencies(
        MissionWorkingContext(), OperateStepTurn(new_tasks=(NewTask(task_id="t2", summary="s", blocks=("t1",)),)),
    )
    working = record_task_detail(working, "t1", "a very long verbose account of what t1 actually did")
    working = record_task_detail(working, "t2", "t2's in-progress notes")

    compacted = compact_working_context(state, working, digest=lambda tid, detail: f"[digest:{tid}]")

    assert compacted.full_detail["t1"] == "a very long verbose account of what t1 actually did", \
        "t1 still feeds non-terminal t2 -- must NOT be compacted yet"
    assert compacted.full_detail["t2"] == "t2's in-progress notes"

    # now t2 concludes -- both become eligible, both get digested
    state_after = _state(_task("t1", TaskStatus.DONE), _task("t2", TaskStatus.DONE))
    compacted_after = compact_working_context(state_after, working, digest=lambda tid, detail: f"[digest:{tid}]")
    assert compacted_after.full_detail["t1"] == "[digest:t1]"
    assert compacted_after.full_detail["t2"] == "[digest:t2]"
    # dependents mapping itself is untouched by compaction (it isn't detail)
    assert compacted_after.dependents == working.dependents


def test_compact_working_context_is_pure_never_mutates_its_input():
    state = _state(_task("t1", TaskStatus.DONE))
    working = record_task_detail(MissionWorkingContext(), "t1", "full detail")
    compact_working_context(state, working, digest=lambda tid, detail: "shrunk")
    assert working.full_detail["t1"] == "full detail", "the original MissionWorkingContext must be untouched"
