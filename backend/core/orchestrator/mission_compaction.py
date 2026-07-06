"""
Mission Engine -- §8 compaction (design ref:
proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md §8).

§8 is explicit about scope: compaction acts on "the mission's accumulated
WORKING context (not the graph -- the graph is already durable by
construction)"; "the task graph's structure... never compacts, only verbose
detail." So every function here takes a `MissionState` (already read) and a
`MissionWorkingContext` -- NEVER a `GraphPort` -- which makes "compaction
cannot touch the graph" true by construction, not by convention.

KNOWN LIMITATION, stated plainly rather than glossed over: `MissionWorkingContext
.dependents` (which terminal task still feeds a non-terminal one -- §8's
"frontier" test) is populated ONLY from live `OperateStepTurn.new_tasks`
declarations via `record_turn_dependencies`, in the same turn the graph's
BLOCKS/FEEDS edges are written. There is currently no way to reconstruct it
from the graph after a restart: `GraphPort.write()` persists TASK edges, but
`depends_on`/`dependents_of`/`breaks_if_removed` are hardcoded to the
CodeFile/IMPORTS Cypher pattern (verified directly against
`core/memory/graph_store.py`'s `_traverse`) and `members()` returns nodes
only -- there is no bulk edge-read anywhere on `GraphPort`. So frontier-aware
compaction eligibility is IN-SESSION ONLY today: after a cold restart, the
mirror is empty and every terminal task would read as having no dependents.
Flagged to backend as a real (non-blocking) foundation-seam gap worth a
future TASK-edge-read method -- NOT worked around here by guessing at a
traversal that doesn't exist. Until that lands, a caller resuming from a
restart should treat compaction as unavailable for that session (or fall
back to the coarser `MissionState.all_tasks_terminal()` whole-mission
signal, which needs no dependents at all) rather than trust a rebuilt-empty
mirror.

Storage/distillation mechanics are explicitly NOT this module's job (§8:
"memory's call") -- `digest` is a caller-supplied pure function; this module
only decides WHEN a task is eligible and WHAT gets replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .mission_operate import MissionState, OperateStepTurn


@dataclass(frozen=True, slots=True)
class MissionWorkingContext:
    """The orchestrator-side (never graph-side) accumulated state §8's
    compaction operates on -- carried turn to turn by whatever wires this
    module into the live loop (not yet built; this module only defines the
    shape + the compaction decision over it).

    full_detail: task_id -> the task's full accumulated summary/evidence/
    findings text (verbose, pre-distillation).
    dependents: task_id -> the set of task_ids that depend on it (who feeds
    off or is blocked by it) -- see the module docstring's limitation on how
    this is populated and its in-session-only scope."""
    full_detail: dict[str, str] = field(default_factory=dict)
    dependents: dict[str, frozenset[str]] = field(default_factory=dict)


def record_turn_dependencies(working: MissionWorkingContext, turn: OperateStepTurn) -> MissionWorkingContext:
    """Extends `working.dependents` from this turn's `NewTask.blocks`/`feeds`
    declarations -- the only place a task's dependency relationships are ever
    stated to this module (see the module docstring on why the graph itself
    cannot be read back for this). Pure; returns a new `MissionWorkingContext`."""
    dependents = {k: set(v) for k, v in working.dependents.items()}
    for nt in turn.new_tasks:
        for dep in (*nt.blocks, *nt.feeds):
            dependents.setdefault(dep, set()).add(nt.task_id)
    return MissionWorkingContext(
        full_detail=dict(working.full_detail),
        dependents={k: frozenset(v) for k, v in dependents.items()},
    )


def record_task_detail(working: MissionWorkingContext, task_id: str, detail: str) -> MissionWorkingContext:
    """Records/refreshes a task's full (pre-distillation) detail text. Pure;
    returns a new `MissionWorkingContext`."""
    full_detail = dict(working.full_detail)
    full_detail[task_id] = detail
    return MissionWorkingContext(full_detail=full_detail, dependents=working.dependents)


def compaction_eligible_tasks(state: MissionState, working: MissionWorkingContext) -> frozenset[str]:
    """§8: which terminal tasks are no longer on the mission's current
    frontier -- eligible to have their full detail distilled to a digest and
    dropped from hot working context. A terminal task is eligible iff every
    known dependent is ALSO terminal, or it has none recorded. Fail-closed in
    spirit: an unknown dependent (not present in `state.tasks`, e.g. a stale
    or malformed reference) is treated as NOT terminal -- never eligible on
    ambiguous information."""
    eligible = set()
    for task in state.tasks:
        if task.status is None:
            continue  # non-terminal tasks are never eligible (§1 -- not yet asserted)
        deps = working.dependents.get(task.task_id, frozenset())
        if all(_is_terminal_in(state, dep) for dep in deps):
            eligible.add(task.task_id)
    return frozenset(eligible)


def _is_terminal_in(state: MissionState, task_id: str) -> bool:
    dep_task = state.task_by_id(task_id)
    return dep_task is not None and dep_task.status is not None


def compact_working_context(
    state: MissionState, working: MissionWorkingContext, digest: Callable[[str, str], str],
) -> MissionWorkingContext:
    """Applies the §8 compaction decision: every eligible task's full detail
    is replaced by `digest(task_id, full_detail)` -- the actual distillation
    (an LLM summarization call, a durable memory write) is the caller's to
    provide, not this module's (§8: "storage mechanics are memory's"). Never
    touches `state` or any graph -- pure, no I/O, no `GraphPort` in scope."""
    eligible = compaction_eligible_tasks(state, working)
    new_detail = {
        task_id: (digest(task_id, detail) if task_id in eligible else detail)
        for task_id, detail in working.full_detail.items()
    }
    return MissionWorkingContext(full_detail=new_detail, dependents=working.dependents)
