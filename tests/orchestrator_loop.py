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
    assert "hydration" in kinds and "tool_call" in kinds and "answer" in kinds


# --- 2. native gateway run_turn (real registry, offline) --------------------

def _caps():
    discover()
    return Capabilities.open(VrakshaContext.new("s"))


def test_run_turn_routes_tool_through_guard_and_answers():
    from pydantic_ai.models.test import TestModel

    caps = _caps()
    ans = asyncio.run(caps.run_turn(
        system_prompt="orchestrate",
        user_prompt="compute 2+2",
        output_type=OrchestratorAnswer,
        model=TestModel(call_tools=["math_calculator"]),
    ))
    assert isinstance(ans, OrchestratorAnswer)
    # the model's native tool call routed through the guarded handler + recorded
    assert [r.tool_name for r in caps.ctx.tool_calls] == ["math.calculator"]


def test_run_turn_graceful_forced_answer_at_cap():
    from pydantic_ai import ModelResponse
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    def fn(messages, info):
        # call a tool while any are offered; once tools are withheld, answer.
        if info.function_tools:
            return ModelResponse(parts=[ToolCallPart(
                tool_name=info.function_tools[0].name, args={"expression": "2+2"})])
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
