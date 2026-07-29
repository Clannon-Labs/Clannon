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
import time

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelResponse
from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from foundation import (
    BatchAwarenessItem, BatchLifecycleStatus, CrossBatchAwareness, PermissionLevel, VrakshaContext,
)
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


def _ctx(*, mission_id: str = ""):
    ctx = VrakshaContext.new("s")
    ctx.mission_id = mission_id
    return ctx


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
            domain="research",
            expert_keys=frozenset({"research.investigate"}),
            tool_keys=frozenset({"research.read"}),
            system_prompt="test scoped batch prompt",
            grants=frozenset({PermissionLevel.READ}),
        ),
    }


class _FakeAwareness:
    """Records every call it receives, in order -- used to pin the
    read-before/record-after flow (b1-item-3) without a real store."""

    def __init__(self, awareness: CrossBatchAwareness | None = None):
        self._awareness = awareness or CrossBatchAwareness()
        self.record_calls: list[tuple] = []
        self.read_calls: list[tuple] = []

    async def record_batch_status(self, user_id, mission_id, batch_id, domain, status, headline):
        self.record_calls.append((user_id, mission_id, batch_id, domain, status, headline))
        return True

    async def cross_batch_awareness(self, user_id, mission_id, requesting_batch_id):
        self.read_calls.append((user_id, mission_id, requesting_batch_id))
        return self._awareness


def _offered_names(caps, model) -> list[str]:
    offered: list[str] = []

    def spy(messages, info):
        offered.extend(t.name for t in info.function_tools)
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "done", "presentation": "chat", "confidence": 0.5},
        )])

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
                tool_name=out.name,
                args={"answer_text": full_report, "presentation": "chat", "confidence": 0.8},
            )])
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "central final answer", "presentation": "chat", "confidence": 0.9},
        )])

    result = asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))

    assert result.answer_text == "central final answer"
    assert len(ctx.batch_findings) == 1
    finding = ctx.batch_findings[0]
    assert finding.batch == "research"
    assert finding.full_content == full_report, "the FULL batch answer must be buffered, not the excerpt"
    assert finding.metadata["confidence"] == 0.8


# ─── b1-item-3: cross-batch awareness consumption ──────────────────────────

def test_spawn_batch_with_no_awareness_port_is_unchanged_from_before():
    """Regression pin: BatchHandler() without an awareness port (today's real
    default -- wiring.py is the only production construction site, and it now
    always threads a real one, but every OTHER caller, including these older
    tests above, still constructs bare) behaves byte-for-byte as before this
    feature existed. No awareness call is attempted."""
    async def go():
        handler = BatchHandler(batch_registry=_batch_registry(), registry=_registry_with_one_batchable_domain())
        summary = await handler.spawn_batch("no-such-batch", "do something", _ctx(mission_id="m1"))
        assert summary.summary.startswith("[unavailable]")
    asyncio.run(go())


def test_spawn_batch_records_active_then_done_with_a_stable_batch_id():
    """The read-before/record-after flow (b1-item-3 design §5): ACTIVE is
    recorded before the batch's own turn runs, DONE after it succeeds, both
    keyed by the SAME per-invocation batch_id -- batch_key/domain is a
    separate, stable axis (§2/§3), never the row key."""
    reg = _registry_with_one_batchable_domain()
    fake = _FakeAwareness()
    ctx = _ctx(mission_id="m1")
    caps = Capabilities.open(ctx, registry=reg, batch_registry=_batch_registry(), awareness=fake)
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "research", "task": "investigate the thing"})])
        out = info.output_tools[0]
        text = "batch answer" if calls["n"] == 2 else "central final answer"
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": text, "presentation": "chat", "confidence": 0.6},
        )])

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))

    assert len(fake.record_calls) == 2, "one ACTIVE before the turn, one DONE after"
    active_call, done_call = fake.record_calls
    assert active_call[4] == BatchLifecycleStatus.ACTIVE
    assert done_call[4] == BatchLifecycleStatus.DONE
    assert active_call[2] == done_call[2] != "", "same per-invocation batch_id across ACTIVE -> DONE"
    assert active_call[3] == "research" == done_call[3], "domain carries the stable batch_key"
    assert active_call[0] == ctx.user_id and active_call[1] == "m1"
    assert len(fake.read_calls) == 1, "exactly one cross_batch_awareness read, before the turn runs"
    assert fake.read_calls[0] == (ctx.user_id, "m1", active_call[2]), \
        "the read excludes-self key must match the SAME batch_id just recorded ACTIVE"


def test_cross_batch_awareness_folded_into_batch_task_prompt():
    """A non-empty awareness read becomes part of the batch's OWN task prompt
    -- internal to its scoped turn, distinct from what the central model's own
    context ever sees (the two-output split still holds one tier up)."""
    reg = _registry_with_one_batchable_domain()
    other = CrossBatchAwareness(items=[
        BatchAwarenessItem(batch_id="other1", domain="security",
                            status=BatchLifecycleStatus.ACTIVE, headline="scanning for CVEs"),
    ], total_batches=1)
    fake = _FakeAwareness(other)
    ctx = _ctx(mission_id="m1")
    caps = Capabilities.open(ctx, registry=reg, batch_registry=_batch_registry(), awareness=fake)
    captured_prompts: list[str] = []
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "research", "task": "investigate the thing"})])
        if calls["n"] == 2:
            for m in messages:
                if isinstance(m, ModelRequest):
                    captured_prompts.extend(
                        p.content for p in m.parts if isinstance(p, UserPromptPart) and isinstance(p.content, str)
                    )
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "ok", "presentation": "chat", "confidence": 0.6},
        )])

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))

    assert captured_prompts, "the batch's own turn must have received a user prompt"
    assert any("scanning for CVEs" in p and "security" in p for p in captured_prompts), \
        "the other batch's awareness headline must be folded into this batch's own task prompt"


def test_spawn_batch_records_failed_status_when_the_batch_turn_raises():
    """A crashed batch must not vanish from awareness -- otherwise it reads as
    'never existed' to its siblings instead of 'failed', defeating the exact
    quiet-failure case the slice exists to surface (b1-item-3 design §5)."""
    reg = _registry_with_one_batchable_domain()
    fake = _FakeAwareness()
    ctx = _ctx(mission_id="m1")
    caps = Capabilities.open(ctx, registry=reg, batch_registry=_batch_registry(), awareness=fake)
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "research", "task": "investigate the thing"})])
        if calls["n"] == 2:
            raise RuntimeError("batch model exploded")
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "central final answer", "presentation": "chat", "confidence": 0.9},
        )])

    result = asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))

    assert result.answer_text == "central final answer", \
        "a batch fault must not sink the central orchestrator's own turn"
    statuses = [c[4] for c in fake.record_calls]
    assert statuses == [BatchLifecycleStatus.ACTIVE, BatchLifecycleStatus.FAILED]


def test_spawn_batch_records_failed_on_cancellation_and_still_propagates_it():
    """CancelledError is a BaseException, not an Exception -- a bare `except
    Exception` silently misses it, leaving a cancelled batch stuck at ACTIVE
    forever (security review, b1-item-3 follow-up). It must still transition
    to FAILED, and the cancellation itself must never be swallowed."""
    class _CancellingAwareness(_FakeAwareness):
        async def cross_batch_awareness(self, user_id, mission_id, requesting_batch_id):
            await super().cross_batch_awareness(user_id, mission_id, requesting_batch_id)
            raise asyncio.CancelledError()

    async def go():
        fake = _CancellingAwareness()
        handler = BatchHandler(
            batch_registry=_batch_registry(), registry=_registry_with_one_batchable_domain(), awareness=fake,
        )
        with pytest.raises(asyncio.CancelledError):
            await handler.spawn_batch("research", "task", _ctx(mission_id="m1"))
        statuses = [c[4] for c in fake.record_calls]
        assert statuses == [BatchLifecycleStatus.ACTIVE, BatchLifecycleStatus.FAILED], \
            "a cancelled batch must still leave ACTIVE, never stay stuck there"
    asyncio.run(go())


def test_spawn_batch_unconfigured_key_never_records_awareness():
    """The 'not configured' path never resolves a batch_id or a definition --
    there is nothing to record against, unlike a real batch that fails after
    starting (previous test)."""
    async def go():
        fake = _FakeAwareness()
        handler = BatchHandler(
            batch_registry=_batch_registry(), registry=_registry_with_one_batchable_domain(), awareness=fake,
        )
        await handler.spawn_batch("no-such-batch", "do something", _ctx(mission_id="m1"))
        assert fake.record_calls == []
        assert fake.read_calls == []
    asyncio.run(go())


def test_spawn_batch_mints_a_distinct_batch_id_per_invocation():
    """Two spawns of the SAME batch_key must not share a batch_id -- a shared
    id would let a second concurrent same-domain batch clobber the first's
    status row, and cross_batch_awareness (which excludes only the requesting
    batch_id) would then hide both from each other instead of showing two
    distinct 'research' entries (b1-item-3 design §2)."""
    async def go():
        fake = _FakeAwareness()
        handler = BatchHandler(
            batch_registry=_batch_registry(), registry=_registry_with_one_batchable_domain(), awareness=fake,
        )

        async def one_call():
            def spy(messages, info):
                out = info.output_tools[0]
                return ModelResponse(parts=[ToolCallPart(
                    tool_name=out.name,
                    args={"answer_text": "ok", "presentation": "chat", "confidence": 0.5},
                )])
            await handler.spawn_batch("research", "task", _ctx(mission_id="m1"), model=FunctionModel(spy))

        await one_call()
        await one_call()
        active_ids = [c[2] for c in fake.record_calls if c[4] == BatchLifecycleStatus.ACTIVE]
        assert len(active_ids) == 2
        assert active_ids[0] != active_ids[1]
    asyncio.run(go())
