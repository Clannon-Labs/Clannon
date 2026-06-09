"""Tests for the generic registry-driven ExpertHandler (structured invocation,
two-output split, marking, scoped tools, never-silent failures)."""

import asyncio

from pydantic import BaseModel

from foundation import PermissionLevel, VrakshaContext
from registry.capabilities import CapabilityKind, CapabilityRegistry, ExpertSpec, ToolSpec
from registry.capabilities import validate
from registry.capabilities.handler import ExpertHandler
from registry.capabilities import ExpertOutput, ExpertRequest
from registry.capabilities.handler import ToolHandler


class _In(BaseModel):
    prompt: str


def _ctx():
    return VrakshaContext.new("s")


def _expert_reg(impl, *, tools=()):
    reg = CapabilityRegistry()
    spec = ExpertSpec(
        name="fake", kind=CapabilityKind.EXPERT, description="d", domain="dom", impl=impl,
        input_schema=_In, output_schema=ExpertOutput, skills=("s.md",), tool_grants=tools,
    )
    reg.register(spec, validate(spec))
    return reg


def test_two_output_split_and_marking():
    class Fake:
        async def run(self, args, env):
            return ExpertOutput(summary="sum", full_content="FULL " + args.prompt,
                                citations=["http://x"], confidence=0.7)
    ctx = _ctx()
    summaries = asyncio.run(ExpertHandler(registry=_expert_reg(Fake), tools=None).run_experts(
        [ExpertRequest(key="dom.fake", arguments={"prompt": "T"})], ctx))

    assert len(summaries) == 1 and summaries[0].summary == "sum" and summaries[0].expert == "dom.fake"
    # full findings buffered separately; orchestrator only got the summary
    assert len(ctx.expert_findings) == 1 and "FULL T" in ctx.expert_findings[0].full_content
    assert ctx.expert_findings[0].ref == summaries[0].finding_ref
    record = ctx.expert_calls[0]
    assert record.success and record.result["mark"]["has_citations"] is True


def test_unknown_expert_never_silent():
    summaries = asyncio.run(ExpertHandler(registry=CapabilityRegistry(), tools=None).run_experts(
        [ExpertRequest(key="no.body", arguments={"prompt": "T"})], _ctx()))
    assert summaries[0].finding_ref == "" and "unavailable" in summaries[0].summary


def test_bad_arguments_never_silent():
    class Fake:
        async def run(self, args, env):
            return ExpertOutput(summary="x", full_content="x")
    ctx = _ctx()
    # missing required 'prompt' field -> validation failure, surfaced not silenced
    summaries = asyncio.run(ExpertHandler(registry=_expert_reg(Fake)).run_experts(
        [ExpertRequest(key="dom.fake", arguments={})], ctx))
    assert "unavailable" in summaries[0].summary
    assert ctx.expert_calls[0].success is False and "bad arguments" in ctx.expert_calls[0].error


def test_failed_expert_never_silent():
    class Boom:
        async def run(self, args, env):
            raise RuntimeError("boom")
    ctx = _ctx()
    summaries = asyncio.run(ExpertHandler(registry=_expert_reg(Boom)).run_experts(
        [ExpertRequest(key="dom.fake", arguments={"prompt": "T"})], ctx))
    assert "unavailable" in summaries[0].summary
    assert ctx.expert_calls[0].success is False


def test_expert_uses_scoped_tool_recorded_on_ctx():
    class EchoIn(BaseModel):
        text: str

    class EchoOut(BaseModel):
        text: str

    class Echo:
        async def run(self, args):
            return EchoOut(text=args.text.upper())

    class ToolUser:
        async def run(self, args, env):
            rec = await env.toolbox.call("tt.echo", {"text": "hello"})
            return ExpertOutput(summary="used tool", full_content=str(rec.result), confidence=0.5)

    reg = CapabilityRegistry()
    tspec = ToolSpec(name="echo", kind=CapabilityKind.TOOL, description="e", domain="tt", impl=Echo,
                     input_schema=EchoIn, output_schema=EchoOut, permission=PermissionLevel.READ)
    reg.register(tspec, validate(tspec))
    espec = ExpertSpec(name="fake", kind=CapabilityKind.EXPERT, description="d", domain="dom", impl=ToolUser,
                       input_schema=_In, output_schema=ExpertOutput, skills=("s.md",), tool_grants=("tt.echo",))
    reg.register(espec, validate(espec))

    ctx = _ctx()
    summaries = asyncio.run(ExpertHandler(registry=reg, tools=ToolHandler(registry=reg)).run_experts(
        [ExpertRequest(key="dom.fake", arguments={"prompt": "T"})], ctx))

    assert summaries[0].summary == "used tool"
    # an expert's tool call is recorded on ctx.tool_calls (unified audit)
    assert len(ctx.tool_calls) == 1 and ctx.tool_calls[0].success is True
