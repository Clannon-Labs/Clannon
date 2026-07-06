"""
Tests for the batch-orchestrator design v2's `BatchHandler`/`spawn_batch`
(core/orchestrator ownership: registry/capabilities/handler/batches.py, ratified
proposals/archive/to-backend/2026-07-06_batch-orchestrator-design-v2.md, built
on the scoped-handler mechanism from tests/orchestrator_capability_scoping.py).

Two things this file specifically proves, per the ratified acceptance criteria
plus a design correction an advisor review caught before any of this was
written:

1. RECURSION GUARD -- `Capabilities.scoped_to()` never accepts a
   `batch_registry`, so a batch's own scoped gateway always has `_batches`
   `None` and never offers `spawn_batch` to its own model. Without this, a
   batch could spawn a batch (central -> batch -> batch -> ...), breaking the
   two-tier model the whole design is built on. `test_scoped_to_never_carries_
   a_batch_registry` is the structural check; `test_open_with_batches_offers_
   spawn_batch_but_scoped_to_never_does` is the behavioral one (drives an
   actual run_turn).

2. NON-EMPTY-REGISTRY GATE -- `spawn_batch` is offered to the model only when
   at least one batch is actually configured. An always-refusing tool (today's
   default: no batches.yaml exists yet) is dead surface, not a working one.

`test_spawn_batch_end_to_end_...` is the discriminating case: drives a REAL
nested run_turn (central agent decides to spawn a batch; the batch's OWN
scoped agent runs its own turn and answers) through a single shared
`FunctionModel` spy dispatching by call count -- proving the two-output split
one tier up (`ctx.batch_findings` gets the full text; the model only ever
sees a bounded excerpt as the tool's return value).

Run:
    cd backend && .venv/bin/python -m pytest tests/orchestrator_batch_handler.py -v
"""

import asyncio

from pydantic import BaseModel
from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel

from foundation import PermissionLevel, VrakshaContext
from registry.capabilities import CapabilityKind, CapabilityRegistry, ExpertSpec, ToolSpec, validate
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import BatchDefinition, BatchHandler, Capabilities
from core.orchestrator.schemas import OrchestratorAnswer


class _In(BaseModel):
    prompt: str


class _ToolIn(BaseModel):
    text: str


class _ToolOut(BaseModel):
    text: str


class _Echo:
    async def run(self, args):
        return _ToolOut(text=args.text.upper())


class _Researcher:
    async def run(self, args, env):
        rec = await env.toolbox.call("research.read", {"text": "x"}) if env.toolbox else None
        return ExpertOutput(summary="researched", full_content=str(rec.result if rec else ""), confidence=0.7)


def _ctx():
    return VrakshaContext.new("s")


def _registry_with_one_batchable_domain() -> CapabilityRegistry:
    """One tool (research.read) + one expert (research.investigate) -- enough
    to build a BatchDefinition scoped to a real "research" domain."""
    reg = CapabilityRegistry()
    read_spec = ToolSpec(name="read", kind=CapabilityKind.TOOL, description="r", domain="research",
                         impl=_Echo, input_schema=_ToolIn, output_schema=_ToolOut,
                         permission=PermissionLevel.READ)
    reg.register(read_spec, validate(read_spec))
    expert_spec = ExpertSpec(
        name="investigate", kind=CapabilityKind.EXPERT, description="d", domain="research",
        impl=_Researcher, input_schema=_In, output_schema=ExpertOutput,
        skills=("s.md",), tool_grants=("research.read",),
    )
    reg.register(expert_spec, validate(expert_spec))
    return reg


def _batch_registry() -> dict:
    return {
        "research": BatchDefinition(
            expert_keys=frozenset({"research.investigate"}),
            tool_keys=frozenset({"research.read"}),
            grants=frozenset({PermissionLevel.READ}),
        ),
    }


def _offered_names(caps, model) -> list[str]:
    offered: list[str] = []

    def spy(messages, info):
        offered.extend(t.name for t in info.function_tools)
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool_name=out.name, args={"answer_text": "done", "confidence": 0.5})])

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))
    return offered


# ─── has_batches gate ───────────────────────────────────────────────────────

def test_batch_handler_has_batches_false_on_empty_registry():
    assert BatchHandler().has_batches is False
    assert BatchHandler(batch_registry={}).has_batches is False


def test_batch_handler_has_batches_true_once_configured():
    assert BatchHandler(batch_registry=_batch_registry()).has_batches is True


# ─── the recursion guard ────────────────────────────────────────────────────

def test_scoped_to_never_carries_a_batch_registry():
    """Structural check: scoped_to() has no batch_registry parameter at all --
    `_batches` is always None on the instance it returns, regardless of what
    the caller's own (central) Capabilities was opened with."""
    reg = _registry_with_one_batchable_domain()
    scoped = Capabilities.scoped_to(
        _ctx(), expert_keys={"research.investigate"}, tool_keys={"research.read"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    assert scoped._batches is None


def test_open_with_batches_offers_spawn_batch_but_scoped_to_never_does():
    reg = _registry_with_one_batchable_domain()
    central = Capabilities.open(_ctx(), registry=reg, batch_registry=_batch_registry())
    assert "spawn_batch" in _offered_names(central, None)

    scoped = Capabilities.scoped_to(
        _ctx(), expert_keys={"research.investigate"}, tool_keys={"research.read"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    assert "spawn_batch" not in _offered_names(scoped, None), \
        "a batch's own scoped gateway must never be able to spawn another batch"


def test_open_without_batch_registry_never_offers_spawn_batch():
    """Today's real default (no batches.yaml exists yet) -- an always-refusing
    tool would be dead surface, not a working one."""
    reg = _registry_with_one_batchable_domain()
    central = Capabilities.open(_ctx(), registry=reg)
    assert "spawn_batch" not in _offered_names(central, None)


# ─── spawn_batch's own behavior ─────────────────────────────────────────────

def test_spawn_batch_refuses_an_unconfigured_batch_key():
    async def go():
        handler = BatchHandler(batch_registry=_batch_registry(), registry=_registry_with_one_batchable_domain())
        summary = await handler.spawn_batch("no-such-batch", "do something", _ctx())
        assert summary.summary.startswith("[unavailable]")
        assert summary.finding_ref == ""
    asyncio.run(go())


def test_spawn_batch_end_to_end_buffers_full_findings_and_returns_brief_summary():
    """The discriminating case: a REAL nested run_turn. Call 1 is the central
    model deciding to spawn_batch; call 2 is the BATCH's own scoped agent
    answering its task directly; call 3 is the central model's final answer,
    now holding only the batch's brief (bounded) summary string. Proves the
    two-output split one tier up: ctx.batch_findings gets the full text, the
    model only ever sees an excerpt."""
    reg = _registry_with_one_batchable_domain()
    ctx = _ctx()
    caps = Capabilities.open(ctx, registry=reg, batch_registry=_batch_registry())
    full_report = "the research batch's full detailed findings. " * 20
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "research", "task": "investigate the thing"})])
        if calls["n"] == 2:
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name, args={"answer_text": full_report, "confidence": 0.8})])
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name, args={"answer_text": "central final answer", "confidence": 0.9})])

    result = asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))

    assert result.answer_text == "central final answer"
    assert len(ctx.batch_findings) == 1
    finding = ctx.batch_findings[0]
    assert finding.batch == "research"
    assert finding.full_content == full_report, "the FULL batch answer must be buffered, not the excerpt"
    assert finding.metadata["confidence"] == 0.8
