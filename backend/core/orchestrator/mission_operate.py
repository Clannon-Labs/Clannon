"""
Mission Engine -- the §6 operate-step (the gated half of the design ratified
2026-07-05, proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md;
rulings: proposals/archive/to-orchestration/2026-07-05_mission-engine-v2-ratified.md).

Unblocked by `GraphPort.members()` landing on the Protocol (85b4f15). This
module is the per-turn read/write against the graph that `mission.py`'s
ungated functions (`evaluate_completion`, `budget_is_sufficient`) were written
to be called from -- additive to the existing orchestrator loop, no daemon, no
second loop (§6). It is NOT yet wired into `core/orchestrator/loop.py`: per the
Prime Directive, this module plus its `tests/mission_operate.py` verification
is the gate the batch orchestrator crosses before it lands, not a shortcut
around it.

Node identity: never invented here. `GraphNode.node_id` is opaque and
manager-derived -- `GraphPort.write()`'s implementer computes its own id from
`scope` + a label-specific natural-key PROPERTY (`mission_id` for MISSION,
`task_id` for TASK) regardless of what a caller sets on the node it passes in
(verified directly against `core/memory/graph_manager.py`, not assumed). This
module therefore never constructs or parses a node_id: task-to-task edges
(BLOCKS/FEEDS/SUPERSEDES) are written in a SECOND pass, after harvesting the
real, port-assigned `node_id` for every endpoint via `members()` -- the only
way to reference a node correctly without depending on the implementer's
internal id format (which its own contract deliberately keeps opaque). This
also means a conforming fake `GraphPort` and the real `GraphManager` are
interchangeable from this module's point of view -- nothing here is coupled
to Kuzu's specific id scheme.

`success_criteria` is a plain `list[str]` (one string per criterion's
description) -- `core/memory/graph_store.py`'s `Mission` table backs it as a
native Kuzu `STRING[]`, not a JSON blob; `Criterion` only ever carries
`description` today, so the round-trip is `str <-> Criterion(description=str)`.

Conclude-path ruling (2026-07-06,
proposals/archive/to-backend/2026-07-06_conclude-path-signal-design.md):
poll, not push. `conclude_mission()` below writes the single terminal
transition and NOTHING else -- no call into memory, no new contract. Memory
reads that durable record on its own schedule (poll-on-read + a periodic
sweep backstop, both memory's tree to build).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from foundation import (
    BudgetPort,
    BudgetScope,
    EdgeLabel,
    EdgeOrigin,
    GraphEdge,
    GraphNode,
    GraphPort,
    GraphScope,
    NodeLabel,
    PermissionLevel,
)

from .mission import (
    CompletionJudgment,
    Criterion,
    MissionStatus,
    TaskOutcome,
    TaskStatus,
    budget_is_sufficient,
    evaluate_completion,
)

# The only PermissionLevel unambiguously "no side effects" (foundation.vocab.types
# docstring) -- the sole default an autonomous mission may act on without
# escalating to AWAITING_APPROVAL. Which levels beyond READ count as
# autonomous-safe is a product/policy call (THE CODING LAWS §4: business
# values live in config/, not hardcoded here) -- callers may widen this via
# `run_operate_step`'s `autonomous_safe` parameter; this is only the
# conservative default when they don't.
DEFAULT_AUTONOMOUS_SAFE: frozenset[PermissionLevel] = frozenset({PermissionLevel.READ})


# --- shapes the operate-step reads/writes -----------------------------------

@dataclass(frozen=True, slots=True)
class TaskNode:
    """One TASK node as read back from the graph -- the operate-step's own
    projection, distinct from `mission.TaskOutcome` (which is judgment input,
    terminal-only). `node_id` is the real, port-assigned id (from `members()`'s
    `GraphNode.node_id`) -- carried so a later edge-write can reference this
    task without this module ever having to derive an id itself."""
    task_id: str
    node_id: str
    status: TaskStatus | None  # None while non-terminal (active/blocked -- not yet a TaskStatus value)
    summary: str
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class MissionState:
    """Everything one operate-step needs, read fresh from the graph every turn
    (§3's drift-proof anchor: never trusted from working context)."""
    mission_id: str
    intent: str
    criteria: list[Criterion]
    status: MissionStatus
    tasks: list[TaskNode]

    def all_tasks_terminal(self) -> bool:
        return all(t.status is not None for t in self.tasks)

    def task_by_id(self, task_id: str) -> TaskNode | None:
        return next((t for t in self.tasks if t.task_id == task_id), None)


@dataclass(frozen=True, slots=True)
class TaskTransition:
    """This turn's outcome for one already-existing task, moving it to a
    terminal status. Applied as an ASSERTED write (§1 -- once terminal, a task
    joins the durable/immutable record). `summary` is required (mirrors
    `TaskOutcome`): the TASK table's `summary` column is Q1-verified MUTABLE
    (`ON MATCH SET n.summary = r.summary` fires unconditionally), so an
    omitted summary would silently blank out the real one on a repeat write --
    forcing it here removes that footgun at the type level."""
    task_id: str
    status: TaskStatus
    summary: str
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class NewTask:
    """A task the operate-step proposes this turn. `blocks`/`feeds` name
    existing task_ids this new task depends on (§5); `supersedes` names an
    existing task_id this one re-plans (new TASK node + SUPERSEDES edge,
    never a mutation of the old node). `required_permission` is the highest
    `PermissionLevel` this task's capability needs -- above the mission's
    autonomous-safe set, it forces AWAITING_APPROVAL (§7) instead of ACTIVE."""
    task_id: str
    summary: str
    blocks: tuple[str, ...] = ()
    feeds: tuple[str, ...] = ()
    supersedes: str = ""
    required_permission: PermissionLevel = PermissionLevel.READ


@dataclass(frozen=True, slots=True)
class OperateStepTurn:
    """What the caller (eventually the batch orchestrator's turn loop, not yet
    wired) decided this turn -- the operate-step is deliberately not an LLM
    call itself (mission.py's own docstring); it applies decisions already
    made, enforcing every §1/§4/§7 invariant on the way through."""
    transitions: tuple[TaskTransition, ...] = ()
    new_tasks: tuple[NewTask, ...] = ()
    completion_judgment: CompletionJudgment | None = None  # only consulted at PROPOSED_COMPLETE


@dataclass(frozen=True, slots=True)
class OperateStepResult:
    """What happened this turn -- always returned, never raised, on a graph
    fault (degrade-honest, mirrors `GraphResult.degraded`)."""
    status: MissionStatus
    degraded: bool = False
    notes: str = ""


# --- create (the write-once anchor) -----------------------------------------

async def create_mission(
    graph: GraphPort, scope: GraphScope, mission_id: str, intent: str, criteria: list[Criterion],
) -> bool:
    """Writes a MISSION node's write-once anchor for the first time -- `intent`
    and `success_criteria` are `create_only` on the implementer's side (never
    touched again by any later write, enforced by the store itself, not just
    convention); `status` starts `ACTIVE`."""
    node = GraphNode(
        node_id=mission_id, label=NodeLabel.MISSION, scope=scope,
        properties={
            "mission_id": mission_id, "intent": intent,
            "success_criteria": [c.description for c in criteria],
            "status": MissionStatus.ACTIVE.value, "updated_at": time.time(),
        },
    )
    result = await graph.write(scope, [node], [])
    return not result.degraded


# --- read ---------------------------------------------------------------

async def read_mission_state(
    graph: GraphPort, scope: GraphScope, mission_id: str,
) -> MissionState | None:
    """§6 step 1: the anchor (`intent`/`success_criteria`) + current task set,
    both re-read from the graph -- never trusted from working context. Returns
    None on a missing mission or a degraded graph; the caller decides how to
    surface that (never fabricate a state that wasn't actually read).

    Uses `members()`, not `lookup()`, for the MISSION read too: `lookup()`'s
    own implementer hard-restricts point-lookup to `NodeLabel.CODE_FILE`
    (`core/memory/graph_manager.py:104`) -- a bare `label=MISSION` there
    returns empty by construction, always, not just when the mission is
    missing. `members()` has no "one specific MISSION" mode either (its
    `parent_id` filter is a TASK's mission_id, not a MISSION's own id), so
    this reads every MISSION in scope and filters client-side by the
    `mission_id` PROPERTY (never by `node_id`, which is opaque and
    manager-assigned -- see the module docstring). Correct given the current
    contract surface, though a future point-read-by-id would be a welcome
    addition worth flagging to backend if per-user mission counts ever get
    large enough for this to matter."""
    missions_result = await graph.members(scope, NodeLabel.MISSION)
    if missions_result.degraded:
        return None
    mission_node = next(
        (n for n in missions_result.nodes if n.properties.get("mission_id") == mission_id), None,
    )
    if mission_node is None:
        return None

    tasks_result = await graph.members(scope, NodeLabel.TASK, parent_id=mission_id)
    if tasks_result.degraded:
        return None

    criteria = [Criterion(description=d) for d in mission_node.properties.get("success_criteria", [])]
    tasks = [_to_task_node(n) for n in tasks_result.nodes]
    return MissionState(
        mission_id=mission_id,
        intent=mission_node.properties.get("intent", ""),
        criteria=criteria,
        status=MissionStatus(mission_node.properties.get("status", MissionStatus.ACTIVE.value)),
        tasks=tasks,
    )


def _to_task_node(n: GraphNode) -> TaskNode:
    raw_status = n.properties.get("status", "")
    terminal = raw_status in {s.value for s in TaskStatus}
    return TaskNode(
        task_id=n.properties.get("task_id", ""),
        node_id=n.node_id,
        status=TaskStatus(raw_status) if terminal else None,
        summary=n.properties.get("summary", ""),
        evidence=n.properties.get("evidence", ""),
    )


# --- write: advance + propose (§6 steps 3-4) --------------------------------

def _task_node(scope: GraphScope, mission_id: str, task_id: str, *, status: str, summary: str,
                evidence: str = "") -> GraphNode:
    return GraphNode(
        node_id=task_id, label=NodeLabel.TASK, scope=scope,
        properties={
            "task_id": task_id, "mission_id": mission_id, "status": status,
            "summary": summary, "evidence": evidence, "updated_at": time.time(),
        },
    )


async def apply_turn(
    graph: GraphPort, scope: GraphScope, mission_id: str, turn: OperateStepTurn,
) -> tuple[bool, str]:
    """§6 steps 3-4: write this turn's terminal transitions and newly proposed
    tasks, THEN (a separate pass) their dependency/supersession edges. Two
    passes, not one: an edge needs its endpoints' real `node_id`s, which only
    exist once the nodes are persisted -- see the module docstring on why this
    module never derives a node_id itself. Terminal transitions are
    ASSERTED-immutable from here on (§1); a `supersedes` new task is never a
    mutation of the old node -- it is a new TASK node plus a SUPERSEDES edge
    to the one it replaces (§5). Never raises on a graph fault
    (degrade-honest); returns (ok, notes)."""
    nodes: list[GraphNode] = [
        _task_node(scope, mission_id, t.task_id, status=t.status.value, summary=t.summary, evidence=t.evidence)
        for t in turn.transitions
    ] + [
        _task_node(scope, mission_id, nt.task_id, status="active", summary=nt.summary)
        for nt in turn.new_tasks
    ]
    if nodes:
        result = await graph.write(scope, nodes, [])
        if result.degraded:
            return False, result.notes or "graph write (nodes) degraded"

    if not turn.new_tasks:
        return True, "no new tasks/edges to link this turn"

    members_result = await graph.members(scope, NodeLabel.TASK, parent_id=mission_id)
    if members_result.degraded:
        return False, members_result.notes or "graph read (members, for edge linking) degraded"
    node_id_by_task_id = {n.properties.get("task_id"): n.node_id for n in members_result.nodes}

    edges: list[GraphEdge] = []
    unresolved: list[str] = []
    for nt in turn.new_tasks:
        dst = node_id_by_task_id.get(nt.task_id)
        if dst is None:
            unresolved.append(nt.task_id)
            continue
        for blocker in nt.blocks:
            src = node_id_by_task_id.get(blocker)
            if src is None:
                unresolved.append(blocker)
                continue
            edges.append(GraphEdge(src_id=src, dst_id=dst, label=EdgeLabel.BLOCKS))
        for feeder in nt.feeds:
            src = node_id_by_task_id.get(feeder)
            if src is None:
                unresolved.append(feeder)
                continue
            edges.append(GraphEdge(src_id=src, dst_id=dst, label=EdgeLabel.FEEDS))
        if nt.supersedes:
            old = node_id_by_task_id.get(nt.supersedes)
            if old is None:
                unresolved.append(nt.supersedes)
            else:
                edges.append(GraphEdge(src_id=dst, dst_id=old, label=EdgeLabel.SUPERSEDES,
                                        origin=EdgeOrigin.ASSERTED))

    notes = f"unresolved edge endpoint(s): {unresolved}" if unresolved else ""
    if edges:
        result = await graph.write(scope, [], edges)
        if result.degraded:
            return False, result.notes or "graph write (edges) degraded"
    return not unresolved, notes


async def write_mission_status(
    graph: GraphPort, scope: GraphScope, mission_id: str, mission: MissionState,
    status: MissionStatus,
) -> bool:
    """The ONE place a `MISSION` node's status property is (re)written --
    the fast-mutating cursor while non-terminal (§1). `intent`/`success_criteria`
    are re-sent on every call but never actually re-applied: the implementer's
    `create_only` fields are enforced by the store itself past the first write
    (`ON MATCH SET` only ever touches `status`/`updated_at`), not merely by
    convention here."""
    node = GraphNode(
        node_id=mission_id, label=NodeLabel.MISSION, scope=scope,
        properties={
            "mission_id": mission_id, "intent": mission.intent,
            "success_criteria": [c.description for c in mission.criteria],
            "status": status.value, "updated_at": time.time(),
        },
    )
    result = await graph.write(scope, [node], [])
    return not result.degraded


# --- §7 autonomy gate --------------------------------------------------------

def needs_approval(new_tasks: tuple[NewTask, ...],
                    autonomous_safe: frozenset[PermissionLevel] = DEFAULT_AUTONOMOUS_SAFE) -> bool:
    """§7: a proposed task requiring a capability above the mission's
    autonomous-safe set forces `AWAITING_APPROVAL` instead of proceeding
    `ACTIVE`. A policy check over already-declared `PermissionLevel`s, not a
    new enforcement primitive -- the existing grant gates still apply
    independently when the task actually runs."""
    return any(t.required_permission not in autonomous_safe for t in new_tasks)


# --- §6 the whole per-turn sequence ------------------------------------------

async def run_operate_step(
    graph: GraphPort,
    budget: BudgetPort,
    scope: GraphScope,
    budget_scope: BudgetScope,
    mission_id: str,
    estimate: int,
    turn: OperateStepTurn,
    *,
    autonomous_safe: frozenset[PermissionLevel] = DEFAULT_AUTONOMOUS_SAFE,
) -> OperateStepResult:
    """The full §6 sequence for one turn on an active mission:
    read anchor+tasks -> budget pre-check -> autonomy gate -> advance/propose
    -> completion check. Fail-closed and degrade-honest throughout -- never
    raises on a graph/budget fault, never advances past an ambiguous state."""
    mission = await read_mission_state(graph, scope, mission_id)
    if mission is None:
        return OperateStepResult(status=MissionStatus.BLOCKED, degraded=True,
                                  notes=f"mission {mission_id!r} not found or graph degraded")

    if mission.status in (MissionStatus.DONE, MissionStatus.FAILED, MissionStatus.USER_ENDED):
        return OperateStepResult(status=mission.status, notes="mission already concluded; no-op")

    remaining = await budget.remaining(budget_scope)
    if not budget_is_sufficient(remaining, estimate):
        await write_mission_status(graph, scope, mission_id, mission, MissionStatus.BUDGET_PAUSED)
        return OperateStepResult(status=MissionStatus.BUDGET_PAUSED,
                                  notes="insufficient budget for this step's estimate; no model call made")

    if needs_approval(turn.new_tasks, autonomous_safe):
        await write_mission_status(graph, scope, mission_id, mission, MissionStatus.AWAITING_APPROVAL)
        return OperateStepResult(status=MissionStatus.AWAITING_APPROVAL,
                                  notes="a proposed task needs a capability above the autonomous-safe set")

    ok, notes = await apply_turn(graph, scope, mission_id, turn)
    if not ok:
        return OperateStepResult(status=mission.status, degraded=True, notes=notes)

    mission = await read_mission_state(graph, scope, mission_id)
    if mission is None:
        return OperateStepResult(status=MissionStatus.BLOCKED, degraded=True,
                                  notes="graph degraded re-reading state after write")

    if mission.status == MissionStatus.PROPOSED_COMPLETE and turn.completion_judgment is not None \
            and mission.all_tasks_terminal():
        verdict = evaluate_completion(mission.criteria, turn.completion_judgment)
        if verdict == MissionStatus.DONE:
            await conclude_mission(graph, scope, mission_id, mission, MissionStatus.DONE)
            return OperateStepResult(status=MissionStatus.DONE, notes="completion gate passed")
        return OperateStepResult(status=MissionStatus.PROPOSED_COMPLETE,
                                  notes="completion gate held: " + verdict.value)

    return OperateStepResult(status=mission.status, notes=notes)


# --- conclude-path (§4 terminal transition) ---------------------------------

async def conclude_mission(
    graph: GraphPort, scope: GraphScope, mission_id: str, mission: MissionState,
    status: MissionStatus,
) -> bool:
    """The single, clean place a mission reaches a terminal state (`DONE`,
    `FAILED`, or `USER_ENDED`) -- per the v2 ratification's cross-dep #1, the
    one point memory's `clear_mission` keys off. RULED 2026-07-06 (poll, not
    push, proposals/archive/to-backend/2026-07-06_conclude-path-signal-design.md):
    this writes the terminal status and NOTHING else -- no call into memory,
    no new contract. Memory discovers this durable record on its own schedule
    (poll-on-read + a periodic sweep backstop, both memory's tree)."""
    if status not in (MissionStatus.DONE, MissionStatus.FAILED, MissionStatus.USER_ENDED):
        raise ValueError(f"conclude_mission called with a non-terminal status: {status!r}")
    return await write_mission_status(graph, scope, mission_id, mission, status)
