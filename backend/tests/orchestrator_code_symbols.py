"""
CB2 code-symbol tier — ratified design: proposals/archive/to-backend/
2026-07-26_cb2-code-symbol-tier-design.md.

Three layers:
  1. `code_symbols.index_code_symbols` directly, against a fake workspace + a
     hermetic `_FakeGraphPort` (mirrors tests/orchestrator_mission_wiring.py's own
     double: a self-consistent GraphPort with an id scheme deliberately unlike the
     real store's, so a passing test proves decoupling, not accidental format
     agreement) — the bulk of the extraction/resolution correctness proof.
  2. `ExpertHandler._index_code_symbols` — the automatic, server-side wiring
     (no-op without an opted-in graph; records ctx.tool_calls on success/fault).
  3. One real-registry end-to-end proof extending `tests/
     orchestrator_engineering_batch.py`'s own harness, WITH `graph=` threaded
     through `Capabilities.open()` this time — proves the whole opt-in chain
     (batches.yaml's grants_graph -> spawn_batch -> scoped_to(graph=...) ->
     ExpertHandler(graph=...) -> the automatic post-run index).

Run:
    cd backend && .venv/bin/python -m pytest tests/orchestrator_code_symbols.py -v
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import patch

from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel

from foundation import (
    BatchLifecycleStatus, CrossBatchAwareness, EdgeLabel, EdgeOrigin, GraphNode,
    GraphResult, GraphScope, NodeLabel, ToolCallRecord, VrakshaContext,
)
from core.orchestrator.schemas import OrchestratorAnswer
from registry.capabilities import discover
from registry.capabilities.handler import code_symbols
from registry.capabilities.handler.capability import Capabilities
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.support import ExpertEnv, SkillBook
from registry.config.batches import load_batches

# ─── the hermetic GraphPort double ───────────────────────────────────────────

_KEY_PROPERTY = {NodeLabel.MISSION: "mission_id", NodeLabel.ENTITY: "canonical_name"}


@dataclass
class _FakeGraphPort:
    _rows: dict = field(default_factory=lambda: {NodeLabel.MISSION: {}, NodeLabel.ENTITY: {}})
    _edges: list = field(default_factory=list)
    _counter: int = 0
    degrade: bool = False

    def _mint_id(self, label: NodeLabel, natural_key: str) -> str:
        self._counter += 1
        return f"fake#{self._counter}#{label.value}#{natural_key}"

    async def members(self, scope: GraphScope, label: NodeLabel, *, parent_id: str = "") -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        if self.degrade:
            return GraphResult(degraded=True, notes="simulated store fault")
        table = self._rows.get(label, {})
        nodes = [
            GraphNode(node_id=nid, label=label, scope=scope, properties=dict(row["properties"]))
            for nid, row in table.items() if row["scope"] == scope
        ]
        return GraphResult(nodes=nodes)

    async def write(self, scope: GraphScope, nodes: list, edges: list) -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        if self.degrade:
            return GraphResult(degraded=True, notes="simulated store fault")
        applied_nodes = []
        for n in nodes:
            key_prop = _KEY_PROPERTY.get(n.label)
            if key_prop is None:
                continue
            natural_key = n.properties.get(key_prop, "")
            if not natural_key:
                continue
            table = self._rows.setdefault(n.label, {})
            existing_id = next(
                (nid for nid, row in table.items()
                 if row["scope"] == scope and row["properties"].get(key_prop) == natural_key), None,
            )
            if existing_id is None:
                node_id = self._mint_id(n.label, natural_key)
                table[node_id] = {"scope": scope, "properties": dict(n.properties)}
            else:
                node_id = existing_id
                table[node_id]["properties"].update(n.properties)
            applied_nodes.append(GraphNode(node_id=node_id, label=n.label, scope=scope,
                                            properties=dict(table[node_id]["properties"])))
        applied_edges = []
        for e in edges:
            existing = next((x for x in self._edges if x["src"] == e.src_id and x["dst"] == e.dst_id
                              and x["label"] == e.label), None)
            if existing is None:
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

    async def edges_of(self, scope, node_id, label):
        return GraphResult()

    def entity(self, canonical_name: str) -> dict | None:
        return next((row["properties"] for row in self._rows[NodeLabel.ENTITY].values()
                     if row["properties"].get("canonical_name") == canonical_name), None)

    def calls_between(self, src_canonical: str, dst_canonical: str) -> bool:
        src_id = next((nid for nid, row in self._rows[NodeLabel.ENTITY].items()
                        if row["properties"].get("canonical_name") == src_canonical), None)
        dst_id = next((nid for nid, row in self._rows[NodeLabel.ENTITY].items()
                        if row["properties"].get("canonical_name") == dst_canonical), None)
        return any(e["src"] == src_id and e["dst"] == dst_id and e["label"] == EdgeLabel.CALLS for e in self._edges)


class _FakeWorkspace:
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
    async def write_bytes(self, rel_path, data): self.files[rel_path] = data
    async def read_bytes(self, rel_path): return self.files[rel_path]
    async def list(self): return sorted(self.files)


def _ctx(mission_id: str = "") -> VrakshaContext:
    ctx = VrakshaContext.new("s")
    ctx.mission_id = mission_id
    return ctx


# ─── layer 1: extraction/resolution correctness ─────────────────────────────

def test_writes_entity_nodes_for_python_definitions():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n\nclass Baz:\n    pass\n"})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 2 and calls == 0
    assert graph.entity("a.py::foo") == {"canonical_name": "a.py::foo", "entity_type": "function"}
    assert graph.entity("a.py::Baz") == {"canonical_name": "a.py::Baz", "entity_type": "class"}


def test_writes_calls_edge_between_two_resolved_functions():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    bar()\n\ndef bar():\n    pass\n"})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 2 and calls == 1
    assert graph.calls_between("a.py::foo", "a.py::bar")


def test_ambiguous_callee_name_is_silently_unresolved():
    ws = _FakeWorkspace({
        "a.py": b"def helper():\n    pass\n\ndef caller():\n    helper()\n",
        "b.py": b"def helper():\n    pass\n",
    })
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    # two files each define "helper" -- ambiguous, so the call from a.py::caller
    # is never written as a CALLS edge to either
    assert error == "" and entities == 3 and calls == 0
    assert not graph.calls_between("a.py::caller", "a.py::helper")
    assert not graph.calls_between("a.py::caller", "b.py::helper")


def test_unresolved_callee_is_silently_dropped_not_an_error():
    ws = _FakeWorkspace({"a.py": b"def caller():\n    nowhere_defined()\n"})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 1 and calls == 0


def test_module_level_call_has_no_caller_entity_and_is_dropped():
    ws = _FakeWorkspace({"a.py": b"def bar():\n    pass\n\nbar()\n"})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 1 and calls == 0   # the top-level bar() call has no enclosing function


def test_c_struct_and_function_call_resolve():
    src = b"struct Point { int x; };\nint foo(void) {\n  return bar();\n}\nint bar(void) {\n  return 1;\n}\n"
    ws = _FakeWorkspace({"a.c": src})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 3 and calls == 1
    assert graph.entity("a.c::Point")["entity_type"] == "struct"
    assert graph.calls_between("a.c::foo", "a.c::bar")


def test_derived_from_mission_when_mission_node_exists():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    graph = _FakeGraphPort()
    ctx = _ctx("m1")
    scope = GraphScope(user_id=ctx.user_id)
    asyncio.run(graph.write(scope, [GraphNode(node_id="", label=NodeLabel.MISSION, scope=scope,
                                               properties={"mission_id": "m1"})], []))
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, ctx, ws))
    assert error == "" and entities == 1
    entity_id = next(iter(graph._rows[NodeLabel.ENTITY]))
    mission_id_real = next(iter(graph._rows[NodeLabel.MISSION]))
    assert any(e["src"] == entity_id and e["dst"] == mission_id_real and e["label"] == EdgeLabel.DERIVED_FROM
               for e in graph._edges)


def test_missing_mission_node_skips_derived_from_but_still_writes_entities():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    graph = _FakeGraphPort()
    ctx = _ctx("m1")   # mission_id set, but no MISSION node was ever written
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, ctx, ws))
    assert error == "" and entities == 1
    assert graph._edges == []


def test_no_mission_writes_entities_with_no_derived_from_attempt():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 1 and graph._edges == []


def test_no_symbols_in_workspace_is_a_clean_zero_not_an_error():
    ws = _FakeWorkspace({"README.md": b"just docs\n"})
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert error == "" and entities == 0 and calls == 0


def test_repeat_scan_merges_not_duplicates():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    graph = _FakeGraphPort()
    asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert len(graph._rows[NodeLabel.ENTITY]) == 1   # same canonical_name -> one row, not two


def test_degraded_graph_fails_closed_with_a_note():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    graph = _FakeGraphPort(degrade=True)
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), ws))
    assert entities == 0 and calls == 0 and error != ""


def test_unlistable_workspace_fails_closed_with_a_note():
    class _Flaky(_FakeWorkspace):
        async def list(self):
            raise OSError("disk fault")
    graph = _FakeGraphPort()
    entities, calls, error = asyncio.run(code_symbols.index_code_symbols(graph, _ctx(), _Flaky()))
    assert entities == 0 and calls == 0 and "disk fault" in error


# ─── layer 2: ExpertHandler wiring ───────────────────────────────────────────

def _env(ws):
    return ExpertEnv(module_dir=None, model_role="code", skills=SkillBook("/", ()),
                      toolbox=None, granted=[], workspace=ws)


def test_index_code_symbols_is_a_noop_without_an_opted_in_graph():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    handler = ExpertHandler()   # graph=None, the default
    ctx = _ctx()
    asyncio.run(handler._index_code_symbols(_env(ws), ctx))
    assert ctx.tool_calls == []


def test_index_code_symbols_records_success_on_ctx_tool_calls():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    graph = _FakeGraphPort()
    handler = ExpertHandler(graph=graph)
    ctx = _ctx()
    asyncio.run(handler._index_code_symbols(_env(ws), ctx))
    assert len(ctx.tool_calls) == 1
    rec: ToolCallRecord = ctx.tool_calls[0]
    assert rec.tool_name == "graph.index_symbols" and rec.success is True
    assert rec.result == {"entities": 1, "calls_edges": 0}


def test_index_code_symbols_records_failure_on_a_degraded_graph():
    ws = _FakeWorkspace({"a.py": b"def foo():\n    pass\n"})
    handler = ExpertHandler(graph=_FakeGraphPort(degrade=True))
    ctx = _ctx()
    asyncio.run(handler._index_code_symbols(_env(ws), ctx))
    assert len(ctx.tool_calls) == 1 and ctx.tool_calls[0].success is False


def test_scoped_threads_graph_through_narrowing():
    graph = _FakeGraphPort()
    handler = ExpertHandler(graph=graph).scoped(allowed_keys={"code.engineer"})
    assert handler._graph is graph


# ─── layer 3: real-registry end-to-end (the opt-in chain, not just the unit) ─

class _FakeAwareness:
    def __init__(self):
        self._awareness = CrossBatchAwareness()
    async def record_batch_status(self, user_id, mission_id, batch_id, domain, status, headline):
        return True
    async def cross_batch_awareness(self, user_id, mission_id, requesting_batch_id):
        return self._awareness


def test_engineering_batch_indexes_symbols_end_to_end_when_grants_graph_opts_in():
    """The whole chain, real registry + real batches.yaml (grants_graph: true) +
    real code.engineer: spawn_batch -> the batch's own scoped Capabilities gets a
    GraphPort (because engineering opted in) -> ExpertHandler(graph=...) ->
    _run_one's automatic post-run index -> the fake graph receives the written
    file's function as an ENTITY node. Nothing about this test's SPY script differs
    from tests/orchestrator_engineering_batch.py's own -- the only difference is
    `graph=` on Capabilities.open()."""
    discover()
    graph = _FakeGraphPort()
    ctx = VrakshaContext.new("s-symbols")
    ctx.mission_id = "m1"
    caps = Capabilities.open(ctx, batch_registry=load_batches(), awareness=_FakeAwareness(), graph=graph)
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "engineering", "task": "write foo.py"},
            )])
        if calls["n"] == 2:
            tool = next(t for t in info.function_tools if t.name == "code_engineer")
            return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args={"prompt": "write foo.py"})])
        if calls["n"] == 3:
            tool = next(t for t in info.function_tools if t.name == "fs_write")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"path": "foo.py", "content": "def foo():\n    pass\n"},
            )])
        if calls["n"] == 4:
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name,
                args={"summary": "wrote foo.py", "full_content": "foo.py written", "confidence": 0.85},
            )])
        if calls["n"] == 5:
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name,
                args={"answer_text": "foo.py written", "presentation": "chat", "confidence": 0.8},
            )])
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "done", "presentation": "chat", "confidence": 0.9},
        )])

    model = FunctionModel(spy)
    with patch("core.llm.framework.model_for_layer", return_value=model):
        result = asyncio.run(caps.run_turn(
            system_prompt="orchestrate", user_prompt="engineering task", output_type=OrchestratorAnswer,
            model=model,
        ))

    assert result.answer_text == "done"
    assert graph.entity("foo.py::foo") == {"canonical_name": "foo.py::foo", "entity_type": "function"}
    index_calls = [r for r in ctx.tool_calls if r.tool_name == "graph.index_symbols"]
    assert len(index_calls) == 1 and index_calls[0].success is True
