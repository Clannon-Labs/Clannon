"""
Orchestrator turn tests, two layers:
  1. run_loop — hydrate, stream the decision log, map the answer + link findings
     (driven by a fake capability door; no model).
  2. the native gateway `Capabilities.run_turn` — real registry, offline via
     TestModel / FunctionModel: tools route through the guards, and the turn cap
     gracefully forces a final answer.
"""

import asyncio

from foundation import NormalizedInput, OrchestratorResponse, VrakshaContext
from core.memory import MemoryManager
from core.orchestrator import loop as loop_mod
from core.orchestrator.ports import Ports
from core.orchestrator.schemas import OrchestratorAnswer
from core.orchestrator.utils.decision_log import CtxDecisionLog
from registry.capabilities import ExpertFindings, discover
from registry.capabilities.handler import Capabilities


def _norm():
    return NormalizedInput(modality="text", content_type="text/plain", content="hi")


# --- 1. run_loop (fake gateway) ---------------------------------------------

class _FakeCaps:
    """A fake capability door: run_turn streams one tool call via on_event, records
    a finding on ctx, and returns a canned OrchestratorAnswer — no model."""

    def __init__(self, ctx):
        self.ctx = ctx

    async def run_turn(self, *, system_prompt, user_prompt, output_type, on_event=None, **kw):
        if on_event is not None:
            await on_event({"tool": "math.calculator", "args": {}})
        self.ctx.expert_findings.append(
            ExpertFindings(expert="web.research", ref="r1", full_content="full")
        )
        return OrchestratorAnswer(answer_text="done", confidence=0.7)


def _ports(ctx):
    return Ports(memory=MemoryManager(), caps=_FakeCaps(ctx), log=CtxDecisionLog(ctx))


def test_run_loop_maps_answer_logs_and_links_findings():
    ctx = VrakshaContext.new("s")
    resp = asyncio.run(loop_mod.run_loop(_norm(), _ports(ctx), ctx))

    assert isinstance(resp, OrchestratorResponse)
    assert resp.text == "done" and resp.confidence == 0.7
    assert resp.finding_refs == ["r1"]                      # linked from ctx.expert_findings
    kinds = [e.kind for e in ctx.decision_log]
    assert "tool_call" in kinds and "answer" in kinds
    assert "hydration" not in kinds                         # memory is INVISIBLE — no hydration notice


# --- 2. native gateway run_turn (real registry, offline) --------------------

def _caps():
    discover()
    return Capabilities.open(VrakshaContext.new("s"))


def test_run_turn_routes_a_tool_call_through_the_guard():
    # a native tool call still routes through the guarded handler and is recorded. Driven
    # by FunctionModel, which advertises native tool search, so the full roster (incl. the
    # deferred calculator) is directly callable — no discovery step needed to exercise the guard.
    from pydantic_ai import ModelResponse
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    called = {"done": False}

    def fn(messages, info):
        names = {t.name for t in info.function_tools}
        if "math_calculator" in names and not called["done"]:
            called["done"] = True
            return ModelResponse(parts=[ToolCallPart(tool_name="math_calculator", args={"expression": "2+2"})])
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool_name=out.name, args={"answer_text": "4", "confidence": 0.9})])

    caps = _caps()
    ans = asyncio.run(caps.run_turn(
        system_prompt="orchestrate",
        user_prompt="compute 2+2",
        output_type=OrchestratorAnswer,
        model=FunctionModel(fn),
    ))
    assert isinstance(ans, OrchestratorAnswer)
    assert [r.tool_name for r in caps.ctx.tool_calls] == ["math.calculator"]   # routed + recorded


def test_run_turn_defers_the_long_tail_behind_tool_search():
    # W2: only the hot path (+ remember) is offered up front; the long tail is hidden behind
    # tool search until the model looks for it. Driven by TestModel, which has no native tool
    # search, so it uses the local `search_tools` fallback that actually hides deferred tools;
    # call_tools=[] so none of the (network/LLM-backed) hot tools actually fire.
    from pydantic_ai.models.test import TestModel

    tm = TestModel(call_tools=[])
    caps = _caps()
    asyncio.run(caps.run_turn(
        system_prompt="orchestrate",
        user_prompt="x",
        output_type=OrchestratorAnswer,
        model=tm,
    ))
    offered = {t.name for t in tm.last_model_request_parameters.function_tools}
    assert {"remember", "search_web"} <= offered      # hot path + remember are eager, up front
    assert "search_tools" in offered                  # discovery is available
    assert "math_calculator" not in offered           # the long tail is hidden until discovered
    assert "media_analyst" not in offered


def test_run_turn_graceful_forced_answer_at_cap():
    from pydantic_ai import ModelResponse
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    def fn(messages, info):
        # call an always-eager tool while any are offered; once tools are withheld, answer.
        names = {t.name for t in info.function_tools}
        if "remember" in names:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="remember", args={"content": "note"})])
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name, args={"answer_text": "forced", "confidence": 0.4})])

    caps = _caps()
    ans = asyncio.run(caps.run_turn(
        system_prompt="orchestrate",
        user_prompt="do it",
        output_type=OrchestratorAnswer,
        max_turns=0,                       # request_limit=1 -> main run caps -> forced pass
        model=FunctionModel(fn),
    ))
    assert ans.answer_text == "forced"


# --- deliverable_ref: a referenced artifact becomes the response text ---------

class _ReportCaps(_FakeCaps):
    """Returns an answer that points at a buffered artifact instead of restating it."""

    def __init__(self, ctx, ref):
        super().__init__(ctx)
        self.ref = ref

    async def run_turn(self, *, system_prompt, user_prompt, output_type, on_event=None, **kw):
        self.ctx.expert_findings.append(
            ExpertFindings(expert="synthesis.writer", ref="w1", full_content="THE FULL REPORT")
        )
        return OrchestratorAnswer(answer_text="lean summary", confidence=0.9, deliverable_ref=self.ref)


def test_run_loop_delivers_referenced_artifact():
    ctx = VrakshaContext.new("s")
    ports = Ports(memory=MemoryManager(), caps=_ReportCaps(ctx, "w1"), log=CtxDecisionLog(ctx))
    resp = asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))

    # the full artifact ships without transiting the model's answer...
    assert resp.text == "THE FULL REPORT"
    # ...while the decision log carries the lean summary
    answers = [e.message for e in ctx.decision_log if e.kind == "answer"]
    assert answers == ["lean summary"]


def test_run_loop_dangling_deliverable_falls_back():
    ctx = VrakshaContext.new("s")
    ports = Ports(memory=MemoryManager(), caps=_ReportCaps(ctx, "nope"), log=CtxDecisionLog(ctx))
    resp = asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))
    assert resp.text == "lean summary"


# --- memory degradation: the turn continues, the user is told the truth ------

def test_memory_fault_degrades_silently():
    class ExplodingMemory:
        async def hydrate(self, request):
            raise RuntimeError("qdrant down")
        async def record_write_proposals(self, *a):
            pass

    ctx = VrakshaContext.new("s")
    ports = Ports(memory=ExplodingMemory(), caps=_FakeCaps(ctx), log=CtxDecisionLog(ctx))
    resp = asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))

    assert resp.text == "done"          # the answer still happened (memory is never a gate)
    assert ctx.hydration_items == []    # no memory this turn
    # memory degrades SILENTLY now — nothing about it reaches the user's decision log
    assert not any("memory" in str(e.message).lower() for e in ctx.decision_log)


def test_degraded_package_is_silent():
    from foundation import HydrationPackage

    class DegradedMemory:
        async def hydrate(self, request):
            return HydrationPackage(degraded=True, notes="memory temporarily unavailable")
        async def record_write_proposals(self, *a):
            pass

    ctx = VrakshaContext.new("s")
    ports = Ports(memory=DegradedMemory(), caps=_FakeCaps(ctx), log=CtxDecisionLog(ctx))
    asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))
    # a degraded package is invisible — no "unavailable" notice in the decision log
    assert not any("unavailable" in str(e.message) for e in ctx.decision_log)


# --- W2 deferred loading: hot path eager, long tail behind tool search ---------

def test_build_orchestrator_tools_defers_the_long_tail():
    from core.llm import Tool
    from registry.capabilities import CapabilityKind
    from registry.capabilities import registry as reg
    from registry.capabilities.handler.support import build_orchestrator_tools

    discover()
    tool_specs = [reg.get_tool(c["key"]) for c in reg.cards(CapabilityKind.TOOL)]
    tool_specs = [s for s in tool_specs if s and not getattr(s.impl, "wants_workspace", False)]
    expert_specs = [reg.get_expert(c["key"]) for c in reg.cards(CapabilityKind.EXPERT)]

    fns = build_orchestrator_tools(tool_specs, expert_specs, on_message=None)
    eager = [f for f in fns if not isinstance(f, Tool)]
    deferred = [f for f in fns if isinstance(f, Tool) and f.defer_loading]

    eager_names = {getattr(f, "__name__", "") for f in eager}
    # remember is always eager; the hot path (web search + research + writer) is eager
    assert "remember" in eager_names
    assert "search_web" in eager_names
    assert {"web_research", "synthesis_writer"} <= eager_names
    # the long tail (media/code/data/verification/... + calculator/fetch/http/python/memory)
    # defers, and there's a lot of it — this is what keeps the eager surface flat
    assert len(deferred) >= 5
    assert len(deferred) > len(eager)
