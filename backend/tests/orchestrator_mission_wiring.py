"""
End-to-end proof for the Mission Engine loop-wiring (ratified design:
proposals/archive/to-backend/2026-07-25_mission-engine-loop-wiring-design.md).

Two layers, mirroring tests/orchestrator_loop.py's own split:
  1. The native tools (start_mission/advance_mission/end_mission) driven through a
     REAL registry (`discover()`) + `Capabilities.run_turn` directly, against a
     hermetic `_FakeGraphPort` (mirrors tests/mission_operate.py's own double: a
     self-consistent GraphPort with an id scheme deliberately unlike the real
     store's, so a passing test proves decoupling, not accidental format
     agreement) + `UnlimitedBudget` (the real production stub, not a fake).
  2. `run_loop`'s own wiring (`_sync_mission_state` runs before `caps.run_turn`,
     `_with_mission_context` folds mission state into the prompt) proven against a
     FAKE capability door (no model) -- `run_loop` always passes `on_event` to
     `caps.run_turn`, which drives pydantic-ai's streaming path; `FunctionModel`
     needs an explicit `stream_function` to support that, which no other test in
     this repo provides yet. Testing the tools via direct `run_turn` calls (no
     `on_event`, matching every other real-registry test) and the loop wiring via
     a fake door (no model at all) proves everything meaningful without taking on
     that unrelated streaming-support gap.

Run:
    cd backend && .venv/bin/python -m pytest tests/orchestrator_mission_wiring.py -v
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from foundation import EdgeOrigin, GraphNode, GraphResult, GraphScope, NodeLabel, NormalizedInput, VrakshaContext
from core.orchestrator import loop as loop_mod
from core.orchestrator.ports import Ports
from core.orchestrator.schemas import OrchestratorAnswer
from core.orchestrator.utils.unlimited_budget import UnlimitedBudget
from registry.capabilities import discover
from registry.capabilities.handler import Capabilities


def _norm():
    return NormalizedInput(modality="text", content_type="text/plain", content="engineer a widget")


# ─── the hermetic GraphPort double (mirrors tests/mission_operate.py's own) ──

_MISSION_CREATE_ONLY = frozenset({"mission_id", "intent", "success_criteria"})
_TASK_CREATE_ONLY = frozenset({"task_id", "mission_id"})


@dataclass
class _FakeGraphPort:
    _mission_rows: dict = field(default_factory=dict)
    _task_rows: dict = field(default_factory=dict)
    _edges: list = field(default_factory=list)
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

    async def write(self, scope: GraphScope, nodes: list, edges: list) -> GraphResult:
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
                        continue
                    table[node_id]["properties"][k] = v
            applied_nodes.append(GraphNode(node_id=node_id, label=n.label, scope=scope,
                                            properties=dict(table[node_id]["properties"])))

        applied_edges = []
        for e in edges:
            existing = next((x for x in self._edges if x["src"] == e.src_id and x["dst"] == e.dst_id
                              and x["label"] == e.label), None)
            if existing is not None and existing["origin"] == EdgeOrigin.ASSERTED.value:
                continue
            if existing is not None:
                existing["origin"] = e.origin.value
            else:
                self._edges.append({"src": e.src_id, "dst": e.dst_id, "label": e.label, "origin": e.origin.value})
            applied_edges.append(e)
        return GraphResult(nodes=applied_nodes, edges=applied_edges)

    async def lookup(self, scope, *, label=None, vector_id="", natural_key=""):
        return GraphResult()

    async def depends_on(self, scope, node_id, *, max_hops=1):
        return GraphResult()

    async def dependents_of(self, scope, node_id, *, max_hops=1):
        return GraphResult()

    async def breaks_if_removed(self, scope, node_id):
        return GraphResult()


def _ctx(session_id: str) -> VrakshaContext:
    return VrakshaContext.new(session_id)


def _caps(ctx, graph, budget) -> Capabilities:
    discover()
    return Capabilities.open(ctx, graph=graph, budget=budget)


def _final_answer(text: str, confidence: float = 0.8):
    def make(info):
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool_name=out.name, args={"answer_text": text, "confidence": confidence})])
    return make


# ─── structural gate — tools offered only when graph+budget both present ────

def test_mission_tools_offered_only_when_graph_and_budget_both_present():
    ctx = _ctx("s-gate")
    caps_with = _caps(ctx, _FakeGraphPort(), UnlimitedBudget())
    tm = TestModel(call_tools=[])
    asyncio.run(caps_with.run_turn(
        system_prompt="orchestrate", user_prompt="x", output_type=OrchestratorAnswer, model=tm,
    ))
    offered = {t.name for t in tm.last_model_request_parameters.function_tools}
    assert {"start_mission", "advance_mission", "end_mission"} <= offered

    ctx2 = _ctx("s-gate-2")
    caps_without = _caps(ctx2, None, None)
    tm2 = TestModel(call_tools=[])
    asyncio.run(caps_without.run_turn(
        system_prompt="orchestrate", user_prompt="x", output_type=OrchestratorAnswer, model=tm2,
    ))
    offered2 = {t.name for t in tm2.last_model_request_parameters.function_tools}
    assert not ({"start_mission", "advance_mission", "end_mission"} & offered2)


def test_scoped_to_never_gets_graph_or_budget():
    """Recursion guard, same shape as batches: a batch's own scoped turn never
    starts/advances/ends a mission."""
    discover()
    scoped = Capabilities.scoped_to(
        _ctx("s-scope"), expert_keys=set(), tool_keys=set(), grants=frozenset(),
    )
    assert scoped._graph is None
    assert scoped._budget is None


# ─── the native tools, real registry, direct run_turn (no on_event) ─────────

def test_start_mission_sets_ctx_mission_id_and_writes_the_graph():
    ctx = _ctx("s-start")
    graph = _FakeGraphPort()
    caps = _caps(ctx, graph, UnlimitedBudget())
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "start_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name,
                args={"intent": "build a widget", "success_criteria": ["widget compiles", "widget passes tests"]},
            )])
        return _final_answer("starting the mission now")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="build me a widget", output_type=OrchestratorAnswer,
        model=FunctionModel(spy),
    ))

    assert ctx.mission_id == "s-start"                    # session_id, per §1
    assert len(graph._mission_rows) == 1
    row = next(iter(graph._mission_rows.values()))
    assert row["properties"]["mission_id"] == "s-start"
    assert row["properties"]["success_criteria"] == ["widget compiles", "widget passes tests"]


def test_start_mission_refuses_when_a_mission_is_already_active():
    ctx = _ctx("s-double-start")
    ctx.mission_id = "s-double-start"    # simulate an already-active mission
    graph = _FakeGraphPort()
    caps = _caps(ctx, graph, UnlimitedBudget())
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "start_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"intent": "another one", "success_criteria": []},
            )])
        return _final_answer("noted")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="start another mission", output_type=OrchestratorAnswer,
        model=FunctionModel(spy),
    ))
    assert graph._mission_rows == {}     # refused before any write


def test_advance_mission_progresses_then_completes_and_clears_mission_id():
    graph = _FakeGraphPort()
    budget = UnlimitedBudget()
    session = "s-advance"

    # step 1: start
    ctx = _ctx(session)
    caps = _caps(ctx, graph, budget)
    calls1 = {"n": 0}

    def spy_start(messages, info):
        calls1["n"] += 1
        if calls1["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "start_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"intent": "ship it", "success_criteria": ["it ships"]},
            )])
        return _final_answer("ok")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="start", output_type=OrchestratorAnswer, model=FunctionModel(spy_start),
    ))
    assert ctx.mission_id == session

    # step 2: advance with one new task (same ctx — one session, mission still active)
    calls2 = {"n": 0}

    def spy_advance(messages, info):
        calls2["n"] += 1
        if calls2["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "advance_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name,
                args={
                    "new_tasks": [{"task_id": "t1", "summary": "write the code"}],
                    "transitions": [], "completion_verdicts": [],
                },
            )])
        return _final_answer("logged the task")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="advance", output_type=OrchestratorAnswer, model=FunctionModel(spy_advance),
    ))
    assert ctx.mission_id == session       # still active — not proposing completion yet
    assert len(graph._task_rows) == 1

    # step 3: complete the task, then propose the mission is done
    calls3 = {"n": 0}

    def spy_complete(messages, info):
        calls3["n"] += 1
        if calls3["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "advance_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name,
                args={
                    "new_tasks": [],
                    "transitions": [{"task_id": "t1", "status": "done", "summary": "wrote the code"}],
                    "completion_verdicts": [{"description": "it ships", "met": True, "evidence": "shipped"}],
                },
            )])
        return _final_answer("mission complete")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="complete", output_type=OrchestratorAnswer, model=FunctionModel(spy_complete),
    ))
    assert ctx.mission_id == ""            # cleared: the mission concluded this step

    mission_row = next(iter(graph._mission_rows.values()))
    assert mission_row["properties"]["status"] == "done"


def test_advance_mission_refuses_without_an_active_mission():
    ctx = _ctx("s-no-mission")
    graph = _FakeGraphPort()
    caps = _caps(ctx, graph, UnlimitedBudget())
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "advance_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name,
                args={"new_tasks": [{"task_id": "t1", "summary": "x"}], "transitions": [], "completion_verdicts": []},
            )])
        return _final_answer("noted")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="advance", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))
    assert graph._task_rows == {}    # refused — no active mission to advance


def test_end_mission_aborts_without_claiming_success():
    graph = _FakeGraphPort()
    budget = UnlimitedBudget()
    session = "s-end"
    ctx = _ctx(session)
    caps = _caps(ctx, graph, budget)
    calls1 = {"n": 0}

    def spy_start(messages, info):
        calls1["n"] += 1
        if calls1["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "start_mission")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"intent": "try something", "success_criteria": ["it works"]},
            )])
        return _final_answer("started")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="start", output_type=OrchestratorAnswer, model=FunctionModel(spy_start),
    ))
    assert ctx.mission_id == session

    calls2 = {"n": 0}

    def spy_end(messages, info):
        calls2["n"] += 1
        if calls2["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "end_mission")
            return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args={"reason": "user asked to stop"})])
        return _final_answer("stopped")(info)

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="stop", output_type=OrchestratorAnswer, model=FunctionModel(spy_end),
    ))
    assert ctx.mission_id == ""
    row = next(iter(graph._mission_rows.values()))
    assert row["properties"]["status"] == "user_ended"


# ─── loop.py's own wiring: read-first + fold-into-prompt (fake door, no model) ──

class _FakeCaps:
    """Records the user_prompt it was given and returns a canned answer — proves
    what run_loop DOES before calling caps.run_turn, not what a real model does."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.received_prompt = ""

    async def run_turn(self, *, system_prompt, user_prompt, output_type, on_event=None, **kw):
        self.received_prompt = user_prompt
        return OrchestratorAnswer(answer_text="done", confidence=0.7)


def _fake_ports(ctx, graph):
    from core.memory import MemoryManager
    from core.orchestrator.utils.decision_log import CtxDecisionLog
    caps = _FakeCaps(ctx)
    return Ports(memory=MemoryManager(), caps=caps, log=CtxDecisionLog(ctx), graph=graph, budget=UnlimitedBudget()), caps


def test_run_loop_sets_mission_id_and_folds_context_before_calling_run_turn():
    graph = _FakeGraphPort()
    ctx = _ctx("s-loop")
    scope = GraphScope(user_id=ctx.user_id)   # matches VrakshaContext.new()'s default user_id
    from core.orchestrator.mission import Criterion
    from core.orchestrator.mission_operate import create_mission
    asyncio.run(create_mission(graph, scope, "s-loop", "ship a feature", [Criterion(description="feature ships")]))

    ports, caps = _fake_ports(ctx, graph)
    asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))

    assert ctx.mission_id == "s-loop"                 # read fresh from the graph before run_turn
    assert "ACTIVE MISSION" in caps.received_prompt
    assert "feature ships" in caps.received_prompt


def test_run_loop_is_an_ordinary_turn_with_no_active_mission():
    ctx = _ctx("s-ordinary")
    ports, caps = _fake_ports(ctx, _FakeGraphPort())
    asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))

    assert ctx.mission_id == ""
    assert "ACTIVE MISSION" not in caps.received_prompt


def test_run_loop_clears_mission_id_when_the_graph_has_no_awareness_port():
    """ports.graph is None (missions unavailable in this Ports instance) --
    degrades to the same no-op as awareness/batches, never crashes."""
    ctx = _ctx("s-no-graph")
    ctx.mission_id = "stale-value-that-must-be-cleared"
    from core.memory import MemoryManager
    from core.orchestrator.utils.decision_log import CtxDecisionLog
    ports = Ports(memory=MemoryManager(), caps=_FakeCaps(ctx), log=CtxDecisionLog(ctx))  # graph=None default
    asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))
    assert ctx.mission_id == ""
