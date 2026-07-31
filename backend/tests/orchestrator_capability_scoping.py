"""
Tests for the batch-orchestrator design v2's scoped-handler mechanism:
`ToolHandler.scoped()` / `ExpertHandler.scoped()` composing (never widening) an
existing restriction, and `Capabilities.scoped_to()` — the new gateway a batch
orchestrator opens, restricted to its own domain's experts/tools.

WHY THE COMPOSE-NEVER-WIDEN FIX MATTERS (found before it could ship as a live
gap, not after): `ExpertHandler._toolbox_for` calls `self._tools.scoped(...)`
for EVERY expert run, passing that expert's OWN registry-declared
`tool_grants` -- not the caller's restriction. Before this fix, `ToolHandler
.scoped()` built a brand-new, unrestricted-except-for-the-new-args handler
from the registry, discarding whatever restriction `self` already had. Inert
while `Capabilities.open()` was the only construction site (always
unrestricted, so narrowing from "everything" was a no-op) -- but the moment a
genuinely restricted `Capabilities.scoped_to()` exists, an expert could reach
a tool outside the batch's own scope via its own tool_grants. Fixed by making
`.scoped()` intersect with the existing restriction on both handlers.

test_scoped_capabilities_expert_cannot_reach_tool_outside_batch_scope is the
discriminating test: it drives an ACTUAL tool call through the real nesting
path (Capabilities.scoped_to -> ExpertHandler._toolbox_for -> ToolHandler
.scoped()), not a private-attribute inspection -- it fails without the fix
(the tool is reachable) and passes with it.
"""

import asyncio

from pydantic import BaseModel
from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel

from foundation import PermissionLevel, VrakshaContext
from registry.capabilities import CapabilityKind, CapabilityRegistry, ExpertSpec, ToolSpec, validate
from registry.capabilities import ExpertOutput, ExpertRequest
from registry.capabilities.handler import Capabilities, ExpertHandler, ToolHandler
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


def _ctx():
    return VrakshaContext.new("s")


def _registry_with(*, expert_tool_grants: tuple[str, ...]) -> CapabilityRegistry:
    """One registry: a read tool (tt.read), a write tool (tt.write), and one
    expert (dom.risky) granted whatever tool keys the caller asks for --
    letting a test declare an expert that's over-privileged relative to a
    batch's own scope, on purpose, to prove the batch scope still holds."""

    called_key = expert_tool_grants[0] if expert_tool_grants else "tt.read"

    class ToolUser:
        # closes over called_key -- impl must be the class itself (validate() inspects
        # spec.impl.run directly), not an instance-producing factory/lambda.
        async def run(self, args, env):
            rec = await env.toolbox.call(called_key, {"text": "x"})
            return ExpertOutput(
                summary="used tool" if rec.success else f"refused: {rec.error}",
                full_content=str(rec.result), confidence=0.5,
            )

    reg = CapabilityRegistry()
    read_spec = ToolSpec(name="read", kind=CapabilityKind.TOOL, description="r", domain="tt",
                          impl=_Echo, input_schema=_ToolIn, output_schema=_ToolOut,
                          permission=PermissionLevel.READ)
    write_spec = ToolSpec(name="write", kind=CapabilityKind.TOOL, description="w", domain="tt",
                           impl=_Echo, input_schema=_ToolIn, output_schema=_ToolOut,
                           permission=PermissionLevel.WRITE)
    reg.register(read_spec, validate(read_spec))
    reg.register(write_spec, validate(write_spec))

    expert_spec = ExpertSpec(
        name="risky", kind=CapabilityKind.EXPERT, description="d", domain="dom",
        impl=ToolUser, input_schema=_In, output_schema=ExpertOutput,
        skills=("s.md",), tool_grants=expert_tool_grants,
    )
    reg.register(expert_spec, validate(expert_spec))
    return reg


# ─── the two .scoped() primitives compose, never widen ────────────────────

def test_tool_handler_scoped_composes_never_widens():
    outer = ToolHandler(allowed_keys={"tt.read", "tt.write"}, grants=frozenset({PermissionLevel.READ, PermissionLevel.WRITE}))
    inner = outer.scoped(allowed_keys={"tt.write", "tt.execute"}, grants=frozenset({PermissionLevel.WRITE, PermissionLevel.EXECUTE}))
    assert inner._allowed_keys == frozenset({"tt.write"}), "must intersect, not replace"
    assert inner._grants == frozenset({PermissionLevel.WRITE}), "must intersect, not replace"


def test_expert_handler_scoped_composes_never_widens():
    outer = ExpertHandler(allowed_keys={"dom.a", "dom.b"})
    inner = outer.scoped(allowed_keys={"dom.b", "dom.c"})
    assert inner._allowed_keys == frozenset({"dom.b"})


# ─── the discriminating test: real nesting, behavioral, not structural ────

def test_scoped_capabilities_expert_cannot_reach_tool_outside_batch_scope():
    """dom.risky is granted tt.write in the registry (over-privileged on its
    own), but the batch's own Capabilities.scoped_to only allows tt.read.
    Without the compose-never-widen fix, _toolbox_for's internal .scoped()
    call would rebuild an unrestricted-except-for-tt.write handler and the
    call below would succeed -- proving the fix by proving the refusal."""
    reg = _registry_with(expert_tool_grants=("tt.write",))
    caps = Capabilities.scoped_to(
        _ctx(), expert_keys={"dom.risky"}, tool_keys={"tt.read"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    summaries = asyncio.run(caps._experts.run_experts(
        [ExpertRequest(key="dom.risky", arguments={"prompt": "go"})], caps.ctx))
    assert summaries[0].summary.startswith("refused"), \
        "the expert's own tool_grants must not escape the batch's tool_keys scope"


def test_scoped_capabilities_refuses_permission_even_when_key_allowed():
    """The batch's tool_keys DOES include tt.write (key allowed) but its
    grants only cover READ -- the permission check must still refuse it."""
    reg = _registry_with(expert_tool_grants=("tt.write",))
    caps = Capabilities.scoped_to(
        _ctx(), expert_keys={"dom.risky"}, tool_keys={"tt.write"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    summaries = asyncio.run(caps._experts.run_experts(
        [ExpertRequest(key="dom.risky", arguments={"prompt": "go"})], caps.ctx))
    assert summaries[0].summary.startswith("refused")


def test_scoped_capabilities_allows_expert_within_scope():
    """The positive case: a batch genuinely scoped to include tt.read (and
    dom.risky granted only tt.read) must still work end to end."""
    reg = _registry_with(expert_tool_grants=("tt.read",))
    caps = Capabilities.scoped_to(
        _ctx(), expert_keys={"dom.risky"}, tool_keys={"tt.read"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    summaries = asyncio.run(caps._experts.run_experts(
        [ExpertRequest(key="dom.risky", arguments={"prompt": "go"})], caps.ctx))
    assert summaries[0].summary == "used tool"


def test_scoped_capabilities_refuses_ungranted_expert_key():
    reg = _registry_with(expert_tool_grants=("tt.read",))
    caps = Capabilities.scoped_to(
        _ctx(), expert_keys={"dom.other"}, tool_keys={"tt.read"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    summaries = asyncio.run(caps._experts.run_experts(
        [ExpertRequest(key="dom.risky", arguments={"prompt": "go"})], caps.ctx))
    assert "not granted" in summaries[0].summary


# ─── run_turn-level: a scoped gateway doesn't even OFFER an ungranted capability ──

def test_run_turn_offers_only_the_scoped_capability_set_to_the_model():
    reg = _registry_with(expert_tool_grants=("tt.read",))
    caps = Capabilities.scoped_to(
        _ctx(), expert_keys={"dom.risky"}, tool_keys={"tt.read"},
        grants=frozenset({PermissionLevel.READ}), registry=reg,
    )
    offered_names: list[str] = []

    def spy(messages, info):
        offered_names.extend(t.name for t in info.function_tools)
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "done", "presentation": "chat", "confidence": 0.5},
        )])

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go", output_type=OrchestratorAnswer,
        model=FunctionModel(spy),
    ))

    # pydantic-ai tool names can't carry a "." -- the handler names them key.replace(".", "_")
    assert "dom_risky" in offered_names
    assert "tt_write" not in offered_names, "an ungranted tool must not even be offered"
    assert "remember" not in offered_names
    assert "recall" in offered_names, "recall (read-only, session-scoped) is unaffected"


def test_open_never_offers_memory_management():
    discover_reg = _registry_with(expert_tool_grants=("tt.read",))
    caps = Capabilities.open(_ctx(), registry=discover_reg)
    offered_names: list[str] = []

    def spy(messages, info):
        offered_names.extend(t.name for t in info.function_tools)
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "done", "presentation": "chat", "confidence": 0.5},
        )])

    asyncio.run(caps.run_turn(
        system_prompt="orchestrate", user_prompt="go",
        output_type=OrchestratorAnswer, model=FunctionModel(spy),
    ))
    assert "remember" not in offered_names
    assert not any(name.startswith("memory_") for name in offered_names)
