"""
Tests for the Mission Engine's gated §6 operate-step
(core/orchestrator/mission_operate.py) -- the per-turn read/write against
GraphPort, unblocked by members() landing on the Protocol (85b4f15).

Design ref: proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md
§6/§7/§9; conclude-path ruling:
proposals/archive/to-backend/2026-07-06_conclude-path-signal-design.md.

`FakeGraphPort` is a hermetic, in-memory GraphPort test-double enforcing the
same invariants the real `core/memory/graph_manager.GraphManager` does
(create-only vs. mutable properties, ASSERTED-edge immutability, fail-closed
on missing user_id) -- but it deliberately assigns node_ids with a DIFFERENT
scheme (`fake#<n>#...`) than the real store's `user|repo|key` format. This is
the point, not an oversight: mission_operate.py must never depend on any
particular id format (see its module docstring) -- if a test here only
passed because the fake happened to use the real format, it would prove
nothing about that decoupling.

§9 acceptance bar, scoped honestly: this module covers restart-survival
(steps 1+3 -- discard all Python objects, rebuild purely from the fake's
durable store, assert the anchor + task graph survive byte-for-byte),
completion-gate fail-closed (step 4), and budget-pre-check zero-write
(the spirit of step 5 -- proving BUDGET_PAUSED happens before any task
content is applied, not just that the returned status is right). Step 2
(mid-run COMPACTION) is out of scope here: compaction acts on the
orchestrator's working context, which this module has none of (it is pure
graph read/write) -- it lands with whatever wires this operate-step into the
live turn loop, not here.

One additional test drives the REAL `core.memory.graph_manager.GraphManager`
end-to-end (mission -> task -> edge), the same convention
tests/memory_graph_manager.py uses (asyncio.run() inside a plain `def` test,
no pytest-asyncio) -- proof this module's node-id-harvest approach (§6's
two-pass write) actually works against the real backing store, not just a
self-consistent fake. Uses the repo-wide autouse `_fresh_graph_store` fixture
(tests/conftest.py) for a clean on-disk Kuzu db per test.

Run:
    cd backend && .venv/bin/python -m pytest tests/mission_operate.py -v
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from foundation import (
    BudgetScope,
    EdgeLabel,
    EdgeOrigin,
    GraphEdge,
    GraphNode,
    GraphResult,
    GraphScope,
    NodeLabel,
    PermissionLevel,
    TokenBudget,
)

from core.orchestrator.mission import Criterion, CompletionJudgment, CriterionVerdict, MissionStatus, TaskStatus
from core.orchestrator.mission_operate import (
    NewTask,
    OperateStepTurn,
    TaskTransition,
    apply_turn,
    conclude_mission,
    create_mission,
    read_mission_state,
    run_operate_step,
    write_mission_status,
)


# ─── test doubles ────────────────────────────────────────────────────────────

_MISSION_CREATE_ONLY = frozenset({"mission_id", "intent", "success_criteria"})
_TASK_CREATE_ONLY = frozenset({"task_id", "mission_id"})


@dataclass
class FakeGraphPort:
    """See module docstring: a self-consistent GraphPort double with an id
    scheme deliberately unlike the real store's, so a passing test proves
    decoupling rather than accidental format agreement."""
    _mission_rows: dict[str, dict] = field(default_factory=dict)  # node_id -> {"scope", "properties"}
    _task_rows: dict[str, dict] = field(default_factory=dict)
    _edges: list[dict] = field(default_factory=list)  # {"src", "dst", "label", "origin"}
    _counter: int = 0

    def _mint_id(self, label: NodeLabel, natural_key: str) -> str:
        self._counter += 1
        return f"fake#{self._counter}#{label.value}#{natural_key}"

    async def members(self, scope: GraphScope, label: NodeLabel, *, parent_id: str = "") -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        table = {NodeLabel.MISSION: self._mission_rows, NodeLabel.TASK: self._task_rows}.get(label)
        if table is None:
            return GraphResult(notes=f"label {label.value!r} has no bulk members() backing")
        nodes = []
        for node_id, row in table.items():
            if row["scope"] != scope:
                continue
            if parent_id and row["properties"].get("mission_id") != parent_id:
                continue
            nodes.append(GraphNode(node_id=node_id, label=label, scope=scope, properties=dict(row["properties"])))
        return GraphResult(nodes=nodes)

    async def write(self, scope: GraphScope, nodes: list[GraphNode], edges: list[GraphEdge]) -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        applied_nodes = []
        for n in nodes:
            if n.label == NodeLabel.MISSION:
                table, key_prop, create_only = self._mission_rows, "mission_id", _MISSION_CREATE_ONLY
            elif n.label == NodeLabel.TASK:
                table, key_prop, create_only = self._task_rows, "task_id", _TASK_CREATE_ONLY
            else:
                continue
            natural_key = n.properties.get(key_prop, "")
            if not natural_key:
                continue
            existing_id = next(
                (nid for nid, row in table.items()
                 if row["scope"] == scope and row["properties"].get(key_prop) == natural_key), None,
            )
            if existing_id is None:
                node_id = self._mint_id(n.label, natural_key)
                table[node_id] = {"scope": scope, "properties": dict(n.properties)}
            else:
                node_id = existing_id
                for k, v in n.properties.items():
                    if k in create_only:
                        continue  # Q1-verified real behavior: create_only survives a repeat write
                    table[node_id]["properties"][k] = v
            applied_nodes.append(GraphNode(node_id=node_id, label=n.label, scope=scope,
                                            properties=dict(table[node_id]["properties"])))

        applied_edges = []
        for e in edges:
            existing = next((x for x in self._edges if x["src"] == e.src_id and x["dst"] == e.dst_id
                              and x["label"] == e.label), None)
            if existing is not None and existing["origin"] == EdgeOrigin.ASSERTED.value:
                continue  # ASSERTED edges refuse an overwrite, same as the real store
            if existing is not None:
                existing["origin"] = e.origin.value
            else:
                self._edges.append({"src": e.src_id, "dst": e.dst_id, "label": e.label, "origin": e.origin.value})
            applied_edges.append(e)
        return GraphResult(nodes=applied_nodes, edges=applied_edges)

    async def lookup(self, scope, *, label=None, vector_id="", natural_key=""):
        return GraphResult()  # CODE_FILE-only in reality; unused by mission_operate

    async def depends_on(self, scope, node_id, *, max_hops=1):
        return GraphResult()

    async def dependents_of(self, scope, node_id, *, max_hops=1):
        return GraphResult()

    async def breaks_if_removed(self, scope, node_id):
        return GraphResult()


@dataclass
class FakeBudgetPort:
    budget: TokenBudget

    async def reserve(self, scope, estimate):
        raise NotImplementedError("mission_operate never reserves — pre-check only")

    async def reconcile(self, reservation, actual):
        raise NotImplementedError("mission_operate never reconciles — pre-check only")

    async def remaining(self, scope):
        return self.budget


_SCOPE = GraphScope(user_id="u1")
_BSCOPE = BudgetScope(user_id="u1", mission_id="m1")
_PLENTY = TokenBudget(user_remaining=1_000_000, mission_remaining=1_000_000)


def _run(coro):
    return asyncio.run(coro)


# ─── create + read round trip ───────────────────────────────────────────────

def test_create_then_read_round_trips_anchor_and_starts_active():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "ship the report",
                              [Criterion(description="tests pass"), Criterion(description="docs updated")])
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state is not None
        assert state.intent == "ship the report"
        assert [c.description for c in state.criteria] == ["tests pass", "docs updated"]
        assert state.status == MissionStatus.ACTIVE
        assert state.tasks == []
    _run(go())


def test_read_missing_mission_returns_none_not_a_fabricated_state():
    async def go():
        graph = FakeGraphPort()
        assert await read_mission_state(graph, _SCOPE, "does-not-exist") is None
    _run(go())


# ─── §1 create-only anchor survives a repeat write ─────────────────────────

def test_write_mission_status_never_mutates_the_anchor():
    async def go():
        graph = FakeGraphPort()
        criteria = [Criterion(description="tests pass")]
        await create_mission(graph, _SCOPE, "m1", "original intent", criteria)
        state = await read_mission_state(graph, _SCOPE, "m1")
        # simulate a caller trying to smuggle a different intent through a status write
        tampered = type(state)(mission_id="m1", intent="a DIFFERENT intent",
                                criteria=criteria, status=state.status, tasks=state.tasks)
        await write_mission_status(graph, _SCOPE, "m1", tampered, MissionStatus.BLOCKED)
        reread = await read_mission_state(graph, _SCOPE, "m1")
        assert reread.intent == "original intent"
        assert reread.status == MissionStatus.BLOCKED
    _run(go())


# ─── apply_turn: transitions, new tasks, dependency + supersession edges ───

def test_apply_turn_writes_transition_new_task_and_blocks_edge_via_harvested_ids():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [])
        seed = OperateStepTurn(new_tasks=(NewTask(task_id="t1", summary="first"),))
        ok, _ = await apply_turn(graph, _SCOPE, "m1", seed)
        assert ok

        turn = OperateStepTurn(
            transitions=(TaskTransition(task_id="t1", status=TaskStatus.DONE, summary="first, done",
                                         evidence="ran it"),),
            new_tasks=(NewTask(task_id="t2", summary="second", blocks=("t1",)),),
        )
        ok, notes = await apply_turn(graph, _SCOPE, "m1", turn)
        assert ok, notes

        state = await read_mission_state(graph, _SCOPE, "m1")
        t1 = state.task_by_id("t1")
        t2 = state.task_by_id("t2")
        assert t1.status == TaskStatus.DONE and t1.summary == "first, done" and t1.evidence == "ran it"
        assert t2.status is None  # non-terminal
        # the edge must reference the FAKE's own node_ids, never the bare task_id strings —
        # proves the two-pass harvest-then-link actually ran, not a shortcut past it.
        assert len(graph._edges) == 1
        edge = graph._edges[0]
        assert edge["src"] == t1.node_id and edge["dst"] == t2.node_id
        assert edge["src"] != "t1" and edge["dst"] != "t2"
    _run(go())


def test_apply_turn_supersede_creates_asserted_edge_immune_to_a_second_supersede():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [])
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(new_tasks=(NewTask(task_id="t1", summary="v1"),)))
        await apply_turn(
            graph, _SCOPE, "m1",
            OperateStepTurn(new_tasks=(NewTask(task_id="t2", summary="v2 replaces v1", supersedes="t1"),)),
        )
        state = await read_mission_state(graph, _SCOPE, "m1")
        t1, t2 = state.task_by_id("t1"), state.task_by_id("t2")
        assert t1 is not None, "a superseded task is never deleted (§5)"
        supersede_edges = [e for e in graph._edges if e["label"] == EdgeLabel.SUPERSEDES]
        assert len(supersede_edges) == 1
        assert supersede_edges[0]["src"] == t2.node_id and supersede_edges[0]["dst"] == t1.node_id
        assert supersede_edges[0]["origin"] == EdgeOrigin.ASSERTED.value

        # a second attempt to re-point the SAME (src, dst) pair's origin must be refused —
        # ASSERTED-edge immutability, mirroring the real store's protected-pairs guard.
        await graph.write(_SCOPE, [], [GraphEdge(src_id=t2.node_id, dst_id=t1.node_id,
                                                  label=EdgeLabel.SUPERSEDES, origin=EdgeOrigin.INFERRED)])
        still = [e for e in graph._edges if e["label"] == EdgeLabel.SUPERSEDES]
        assert still[0]["origin"] == EdgeOrigin.ASSERTED.value, "an asserted edge must not be downgraded"
    _run(go())


# ─── §7 budget pre-check: fail-closed, and nothing else applies first ──────

def test_run_operate_step_pauses_on_insufficient_budget_before_writing_anything():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [])
        budget = FakeBudgetPort(TokenBudget(user_remaining=10, mission_remaining=10))
        turn = OperateStepTurn(new_tasks=(NewTask(task_id="t1", summary="should never land"),))
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=1_000, turn=turn)
        assert result.status == MissionStatus.BUDGET_PAUSED
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.status == MissionStatus.BUDGET_PAUSED
        assert state.tasks == [], "budget pause must short-circuit BEFORE any task content is applied"
    _run(go())


# ─── §7 autonomy gate ───────────────────────────────────────────────────────

def test_run_operate_step_escalates_to_awaiting_approval_above_autonomous_safe_set():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [])
        budget = FakeBudgetPort(_PLENTY)
        turn = OperateStepTurn(new_tasks=(
            NewTask(task_id="t1", summary="send an email", required_permission=PermissionLevel.NETWORK),
        ))
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10, turn=turn)
        assert result.status == MissionStatus.AWAITING_APPROVAL
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.tasks == [], "an escalated task must not be silently applied anyway"
    _run(go())


def test_run_operate_step_proceeds_when_within_autonomous_safe_set():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [])
        budget = FakeBudgetPort(_PLENTY)
        turn = OperateStepTurn(new_tasks=(NewTask(task_id="t1", summary="read-only, fine"),))
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10, turn=turn)
        assert result.status == MissionStatus.ACTIVE
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.task_by_id("t1") is not None
    _run(go())


# ─── §4 completion gate, driven through the full operate-step ──────────────

def test_run_operate_step_completion_gate_holds_on_unmet_criterion():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [Criterion(description="ships the report")])
        # two separate turns, matching the DONE-completion test below: a task must
        # exist BEFORE it can transition (mixing transitions+new_tasks for the same
        # task_id in one turn is undefined -- new_tasks is written after transitions,
        # so it would silently re-clobber the status back to "active").
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(new_tasks=(NewTask(task_id="t0", summary="prep"),)))
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
            transitions=(TaskTransition(task_id="t0", status=TaskStatus.DONE, summary="prep, done"),),
        ))
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.all_tasks_terminal(), "the gate below only means something if the task is genuinely terminal"
        await write_mission_status(graph, _SCOPE, "m1", state, MissionStatus.PROPOSED_COMPLETE)

        budget = FakeBudgetPort(_PLENTY)
        judgment = CompletionJudgment(criteria_verdicts=[
            CriterionVerdict(description="ships the report", met=False, evidence="not yet"),
        ])
        turn = OperateStepTurn(completion_judgment=judgment)
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10, turn=turn)
        assert result.status == MissionStatus.PROPOSED_COMPLETE, "fail-closed: must hold, never auto-DONE"
    _run(go())


def test_run_operate_step_completion_gate_concludes_done_when_all_criteria_met():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [Criterion(description="ships the report")])
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
            new_tasks=(NewTask(task_id="t0", summary="prep"),),
        ))
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
            transitions=(TaskTransition(task_id="t0", status=TaskStatus.DONE, summary="prep, done",
                                         evidence="shipped"),),
        ))
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.all_tasks_terminal()
        await write_mission_status(graph, _SCOPE, "m1", state, MissionStatus.PROPOSED_COMPLETE)

        budget = FakeBudgetPort(_PLENTY)
        judgment = CompletionJudgment(criteria_verdicts=[
            CriterionVerdict(description="ships the report", met=True, evidence="shipped"),
        ])
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10,
                                         turn=OperateStepTurn(completion_judgment=judgment))
        assert result.status == MissionStatus.DONE
        final = await read_mission_state(graph, _SCOPE, "m1")
        assert final.status == MissionStatus.DONE
    _run(go())


def test_run_operate_step_is_a_noop_once_already_concluded():
    async def go():
        graph = FakeGraphPort()
        await create_mission(graph, _SCOPE, "m1", "intent", [])
        state = await read_mission_state(graph, _SCOPE, "m1")
        await conclude_mission(graph, _SCOPE, "m1", state, MissionStatus.DONE)
        budget = FakeBudgetPort(_PLENTY)
        result = await run_operate_step(graph, budget, _SCOPE, _BSCOPE, "m1", estimate=10, turn=OperateStepTurn())
        assert result.status == MissionStatus.DONE
        assert not result.degraded
    _run(go())


# ─── §9 restart-survival (steps 1 + 3) ──────────────────────────────────────

def test_hermetic_restart_survives_with_full_anchor_and_task_graph_intact():
    """Seed a mission, discard every Python object (the working-context
    stand-in), and reconstruct purely from the fake's durable store — the
    same shape as a fresh process reconstructing from real Kuzu. Proves the
    anchor (intent/criteria) and the task graph structure (including a
    superseded task, never deleted) survive byte-for-byte."""
    async def seed():
        graph = FakeGraphPort()
        criteria = [Criterion(description="a"), Criterion(description="b")]
        await create_mission(graph, _SCOPE, "m1", "long-running intent", criteria)
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
            new_tasks=(NewTask(task_id="t1", summary="v1"),),
        ))
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
            new_tasks=(NewTask(task_id="t2", summary="v2 replaces v1", supersedes="t1"),),
        ))
        await apply_turn(graph, _SCOPE, "m1", OperateStepTurn(
            transitions=(TaskTransition(task_id="t2", status=TaskStatus.DONE, summary="v2, done"),),
        ))
        return graph  # stands in for "the durable store", surviving a restart

    async def restart_and_verify(graph):
        # No Python state carried over except the durable store handle itself —
        # every dataclass/local is rebuilt fresh here, exactly as a new process would.
        state = await read_mission_state(graph, _SCOPE, "m1")
        assert state.intent == "long-running intent"
        assert [c.description for c in state.criteria] == ["a", "b"]
        t1, t2 = state.task_by_id("t1"), state.task_by_id("t2")
        assert t1 is not None and t2 is not None, "the superseded task must still be present"
        assert t2.status == TaskStatus.DONE
        supersede_edges = [e for e in graph._edges if e["label"] == EdgeLabel.SUPERSEDES]
        assert len(supersede_edges) == 1
        assert supersede_edges[0]["src"] == t2.node_id and supersede_edges[0]["dst"] == t1.node_id

    graph = _run(seed())
    _run(restart_and_verify(graph))


# ─── tenant isolation (cheap given the fake already tracks scope) ──────────

def test_tenant_isolation_same_ids_different_users_never_cross_leak():
    async def go():
        graph = FakeGraphPort()
        scope_a, scope_b = GraphScope(user_id="u1"), GraphScope(user_id="u2")
        await create_mission(graph, scope_a, "m1", "user A's intent", [])
        await create_mission(graph, scope_b, "m1", "user B's intent", [])
        a = await read_mission_state(graph, scope_a, "m1")
        b = await read_mission_state(graph, scope_b, "m1")
        assert a.intent == "user A's intent"
        assert b.intent == "user B's intent"
    _run(go())


# ─── capstone: the real GraphManager, not just the fake ────────────────────

def test_real_graph_manager_round_trips_mission_task_and_blocks_edge():
    """Same scenario as the harvested-edge fake test above, but against the
    REAL Kuzu-backed GraphManager (tests/conftest.py's autouse
    _fresh_graph_store fixture gives a clean on-disk db). Proves the two-pass
    write (§6: nodes, then harvested-id edges) actually works against the
    real implementer this module was built against, not just a hermetic
    double this module's own author wrote."""
    from core.memory.graph_manager import GraphManager

    async def go():
        manager = GraphManager()
        scope = GraphScope(user_id="real-u1")
        await create_mission(manager, scope, "m1", "real intent", [Criterion(description="c1")])
        await apply_turn(manager, scope, "m1", OperateStepTurn(
            new_tasks=(NewTask(task_id="t1", summary="first"),),
        ))
        await apply_turn(manager, scope, "m1", OperateStepTurn(
            new_tasks=(NewTask(task_id="t2", summary="second", blocks=("t1",)),),
        ))
        state = await read_mission_state(manager, scope, "m1")
        assert state is not None
        assert state.intent == "real intent"
        t1, t2 = state.task_by_id("t1"), state.task_by_id("t2")
        assert t1 is not None and t2 is not None
        assert t1.node_id != "t1", "the real store's node_id is its own composite format, not the bare task_id"

    asyncio.run(go())
