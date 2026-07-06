"""
Mission Engine -- §8 compaction (design ref:
proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md §8).

§8 draws one line: the compaction ACTION never touches the graph ("the task
graph's structure... never compacts, only verbose detail" -- true here by
construction: `compact_working_context` takes an already-decided eligible set
plus a `MissionWorkingContext`, never a `GraphPort`). The eligibility
DECISION is different -- "which terminal tasks are off the frontier" is a
dependency-structure question, and reading that from the graph is not a
graph WRITE, so it doesn't violate §8's spirit. `graph_compaction_eligible_
tasks` below is the (now restart-durable) read; `compact_working_context`
stays the pure action.

History: this module originally carried a `MissionWorkingContext.dependents`
in-session mirror, because `GraphPort` had no bulk TASK-edge read-back --
flagged to backend as a real gap
(proposals/archive/to-backend/2026-07-06_task-edge-read-gap.md). `edges_of()`
has since landed on the Protocol (foundation/contracts/graph.py, 45b6ab4),
explicitly naming this restart-survival need as its first consumer -- so the
mirror was strictly dominated (it only ever agreed with the graph in-session,
and was silently wrong after a restart) and has been removed in favor of
reading dependents straight from the graph.

Storage/distillation mechanics are explicitly NOT this module's job (§8:
"memory's call") -- `digest` is a caller-supplied pure function; this module
only decides WHEN a task is eligible and WHAT gets replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from foundation import EdgeLabel, GraphPort, GraphScope

from .mission_operate import MissionState, TaskNode

_DEPENDENCY_LABELS = (EdgeLabel.BLOCKS, EdgeLabel.FEEDS)


@dataclass(frozen=True, slots=True)
class MissionWorkingContext:
    """The orchestrator-side (never graph-side) accumulated detail §8's
    compaction ACTION operates on -- carried turn to turn by whatever wires
    this module into the live loop (not yet built; this module only defines
    the shape + the compaction action over it).

    full_detail: task_id -> the task's full accumulated summary/evidence/
    findings text (verbose, pre-distillation)."""
    full_detail: dict[str, str] = field(default_factory=dict)


def record_task_detail(working: MissionWorkingContext, task_id: str, detail: str) -> MissionWorkingContext:
    """Records/refreshes a task's full (pre-distillation) detail text. Pure;
    returns a new `MissionWorkingContext`."""
    full_detail = dict(working.full_detail)
    full_detail[task_id] = detail
    return MissionWorkingContext(full_detail=full_detail)


async def graph_compaction_eligible_tasks(
    graph: GraphPort, scope: GraphScope, state: MissionState,
) -> frozenset[str] | None:
    """§8: which terminal tasks are no longer on the mission's frontier --
    eligible to have their full detail distilled to a digest and dropped from
    hot working context. Reads BLOCKS/FEEDS dependents straight from the
    graph via `edges_of()`, so (unlike the old in-session mirror) eligibility
    is correct after a cold restart too.

    A terminal task is eligible iff every task it BLOCKS or FEEDS is ALSO
    terminal, or it has none. `apply_turn` (mission_operate.py) always writes
    `GraphEdge(src_id=<the depended-on task>, dst_id=<the new/dependent
    task>)`, so "tasks this one blocks/feeds" are the edges where it is the
    SRC. `edges_of()` returns every edge incident to a node in EITHER
    direction, so the `e.src_id == task.node_id` filter below is load-
    bearing, not decorative -- drop it and this would count a task's OWN
    blockers as its dependents and invert the eligibility decision.

    Fail-closed on an ambiguous read: returns `None` (never an empty or
    partial set) the moment any `edges_of()` call comes back degraded, so a
    caller can never compact on a graph it couldn't actually read -- treat
    `None` as "skip this compaction pass", not as "nothing to compact". An
    unresolvable dependent (a dst_id not present in `state.tasks`) is
    likewise treated as non-terminal -- never eligible on ambiguous
    information."""
    by_node_id = {t.node_id: t for t in state.tasks}
    eligible: set[str] = set()
    for task in state.tasks:
        if task.status is None:
            continue  # non-terminal tasks are never eligible (§1 -- not yet asserted)
        dependent_node_ids: set[str] = set()
        for label in _DEPENDENCY_LABELS:
            result = await graph.edges_of(scope, task.node_id, label)
            if result.degraded:
                return None
            dependent_node_ids.update(e.dst_id for e in result.edges if e.src_id == task.node_id)
        if all(_is_terminal(by_node_id.get(dst)) for dst in dependent_node_ids):
            eligible.add(task.task_id)
    return frozenset(eligible)


def _is_terminal(task: TaskNode | None) -> bool:
    return task is not None and task.status is not None


def compact_working_context(
    working: MissionWorkingContext, eligible: frozenset[str], digest: Callable[[str, str], str],
) -> MissionWorkingContext:
    """Applies the §8 compaction decision: every eligible task's full detail
    is replaced by `digest(task_id, full_detail)` -- the actual distillation
    (an LLM summarization call, a durable memory write) is the caller's to
    provide, not this module's (§8: "storage mechanics are memory's").
    `eligible` is precomputed (by `graph_compaction_eligible_tasks`) and
    passed in rather than derived here -- this keeps the ACTION pure and
    graph-free even though the DECISION now reads the graph. Never touches
    any graph itself -- pure, no I/O, no `GraphPort` in scope."""
    new_detail = {
        task_id: (digest(task_id, detail) if task_id in eligible else detail)
        for task_id, detail in working.full_detail.items()
    }
    return MissionWorkingContext(full_detail=new_detail)
