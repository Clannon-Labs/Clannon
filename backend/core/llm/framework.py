"""
The single boundary to the LLM framework (PydanticAI).

This is the ONLY module in Vraksha that imports `pydantic_ai`. Every stage that
needs an LLM call (verifier, output filter — one-shot structured; orchestrator and
experts — tool-driving) goes through `build_agent` / `build_tool_agent` +
`run_structured` here. To swap or audit the framework, you edit this one file — no
other module touches the SDK.

What this owns:
- constructing a framework agent for a pipeline layer (model + settings from the
  registry, system prompt from the prompt registry, output schema, retries),
- running it with the shared transient-retry wrapper and per-layer usage limits,
- translating framework/provider failures into foundation errors.

What this does NOT own: Flow, prompts content, schemas, or any orchestration
logic. Callers pass an output schema + a prompt name and get back validated
structured output, never an SDK object.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, TypeVar

from pydantic_ai import Agent, BinaryContent, FunctionToolCallEvent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from core.budget.cost import estimate_call_cost_micros
from foundation import BudgetExhausted, MaxRetriesExceededError, ModelUnavailableError, VrakshaError
from registry.config import get_prompt
import settings

from .registry import model_for_layer, model_name_for_layer, model_settings_for_layer, usage_limits_for_layer
from .retry import run_agent

log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class AgentHandle(Generic[T]):
    """
    Opaque handle to a framework agent. Callers hold this and pass it back to
    `run_structured`; they never touch the underlying SDK object directly, so the
    framework stays replaceable behind this module.
    """
    _agent: Agent[None, T]
    layer: str


@lru_cache(maxsize=None)
def build_agent(
    layer: str,
    *,
    output_type: type[T],
    prompt_name: str,
    retries: int = 2,
) -> AgentHandle[T]:
    """
    Build (and cache) a structured agent for a pipeline layer.

    Framework agents are long-lived, so the result is cached per
    (layer, output_type, prompt_name, retries). `retries` here is the framework's
    malformed-output retry budget; transient provider retries are added at run
    time by `run_agent`. The system prompt is resolved from the prompt registry
    so its version is tracked.
    """
    agent: Agent[None, T] = Agent(
        model_for_layer(layer),
        output_type=output_type,
        system_prompt=get_prompt(prompt_name).text,
        model_settings=model_settings_for_layer(layer),
        retries=retries,
        defer_model_check=True,
    )
    return AgentHandle(agent, layer)


def build_tool_agent(
    model_role: str,
    *,
    output_type: type[T],
    system_prompt: str,
    tools: Sequence[Any] = (),
    deps_type: type | None = None,
    retries: int = 2,
) -> AgentHandle[T]:
    """
    Build a tool-driving agent (used by experts AND the orchestrator).

    Unlike `build_agent`, the system prompt is passed as text (the caller resolves
    it — co-located beside an expert, or from the prompt registry for the
    orchestrator) and the agent is given `tools` it may call during its run. Those
    tools are thin wrappers that route through the guarded ToolHandler/ExpertHandler
    via `deps`, so every guard (grants, permission, SSRF, NETWORK-output
    sanitization, output cap) still applies — the framework never gets raw tool
    access. Not cached: tools/deps are per-run.
    """
    agent: Agent[Any, T] = Agent(
        model_for_layer(model_role),
        output_type=output_type,
        system_prompt=system_prompt,
        model_settings=model_settings_for_layer(model_role),
        deps_type=deps_type,
        tools=list(tools),
        retries=retries,
        defer_model_check=True,
    )
    return AgentHandle(agent, model_role)


def _event_handler(on_tool_event: Callable[[dict], Awaitable[None]]):
    """Adapt pydantic-ai's event stream to a neutral callback: fire `on_tool_event`
    (a plain dict) on each tool call, so callers stream a decision log live without
    importing SDK event types."""
    async def handler(ctx: RunContext[Any], events: AsyncIterable[Any]) -> None:
        async for event in events:
            if isinstance(event, FunctionToolCallEvent):
                await on_tool_event({"tool": event.part.tool_name, "args": event.part.args})
    return handler


def _with_media(prompt: str, media: Sequence[tuple[bytes, str]] | None) -> Any:
    """Build the user prompt: plain text, or — when media is attached — a list of
    [text, BinaryContent...] so a multimodal model sees the bytes alongside the text.
    This is the ONLY place raw media becomes an SDK type, keeping pydantic_ai confined
    here; callers pass neutral (bytes, mime) tuples. Empty/None media → the bare string."""
    if not media:
        return prompt
    parts: list[Any] = [prompt]
    for data, mime in media:
        parts.append(BinaryContent(data=data, media_type=mime))
    return parts


def _to_model_messages(conversation: Sequence[dict] | None) -> list[Any] | None:
    """Convert the foundation-neutral conversation ({"role","content"} dicts,
    oldest first) into PydanticAI ModelMessages. This is the single SDK boundary
    for chat history — foundation never imports pydantic_ai. Unknown/empty turns
    are skipped; an empty result returns None (no history)."""
    if not conversation:
        return None
    messages: list[Any] = []
    for turn in conversation:
        role = turn.get("role")
        content = turn.get("content") or ""
        if not content:
            continue
        if role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages or None


async def run_structured(
    handle: AgentHandle[T],
    prompt: str,
    *,
    deps: Any | None = None,
    max_turns: int | None = None,
    max_output_tokens: int | None = None,
    on_tool_event: Callable[[dict], Awaitable[None]] | None = None,
    model: Any | None = None,
    conversation: Sequence[dict] | None = None,
    media: Sequence[tuple[bytes, str]] | None = None,
) -> T:
    """
    Run an agent and return its validated structured output.

    Adds the shared transient-retry wrapper and per-layer usage limits. `max_turns`
    / `max_output_tokens` are neutral per-run overrides (the SDK `UsageLimits` is
    built here, so callers never import it). `on_tool_event` streams a live decision
    log; `model` overrides the model for this run only (tests inject a TestModel/
    FunctionModel). `media` is a list of neutral (bytes, mime) attachments folded into
    the user message for a multimodal model. Foundation errors propagate unchanged; a usage/turn-cap breach
    becomes `MaxRetriesExceededError` (fail closed at the cap); any other
    framework/provider failure becomes `ModelUnavailableError`.
    """
    limits = usage_limits_for_layer(handle.layer, max_turns=max_turns, max_output_tokens=max_output_tokens)
    esh = _event_handler(on_tool_event) if on_tool_event is not None else None
    history = _to_model_messages(conversation)
    # text by default; [text, BinaryContent...] when a caller attaches media (the
    # media expert passes images here for a multimodal model)
    user_prompt = _with_media(prompt, media)
    # The budget anchor's inputs, built HERE (not in retry.py) because this is the one place
    # both the layer (-> real model id, for pricing) and the live deps (-> mission_id, when this
    # call is inside a mission) are in scope. `deps.ctx` only exists for the orchestrator path
    # (OrchestratorDeps) — every other caller (verifier, filter, memory, experts) naturally gets
    # mission_id="" (no mission ceiling), which is correct: only orchestrator-issued calls are
    # mission-scoped today. See docs/architecture/BUDGET_ENFORCEMENT_ANCHOR.md resolution #2.
    budget_model_id = ""
    budget_estimate_micros = 0
    budget_mission_id = getattr(getattr(deps, "ctx", None), "mission_id", "") or ""
    if settings.BUDGET.enforcement_enabled:
        # Gated on the flag: while enforcement is off (the default), NOTHING here runs — no
        # registry lookup, no pricing lookup — so a model missing from pricing.yaml can never
        # affect a call today. When enforcement IS on, every real layer has already resolved
        # through `model_for_layer` to build this very `handle` (build_agent/build_tool_agent
        # require it), so `model_name_for_layer` cannot fail here in practice; the synthetic
        # `model=` test-override path (AgentHandle built with a fake layer name, bypassing
        # build_agent) never enables enforcement, so it never reaches this branch either.
        #
        # `model_for_layer` returns the RUNNABLE model (may be a FallbackModel wrapping a whole
        # provider chain) — not a pricing key. `model_name_for_layer` gives the single
        # provider-qualified string ("anthropic:claude-sonnet-5"); pricing.yaml keys the bare
        # model id, so strip the provider prefix (matches how `model_name_for_layer` itself
        # already resolves per-run overrides, so this stays override-aware for free).
        budget_model_id = model_name_for_layer(handle.layer).rsplit(":", 1)[-1]
        try:
            budget_estimate_micros = estimate_call_cost_micros(
                model_id=budget_model_id,
                prompt=prompt,
                conversation=conversation,
                media_count=len(media) if media else 0,
                output_tokens_limit=limits.output_tokens_limit,
                elapsed_ceiling_s=settings.ORCHESTRATOR.turn_wall_clock_s,
            )
        except KeyError as exc:
            # cost.py's own fail-closed contract: an un-priced model must BLOCK the spend,
            # never run for free (security review 2026-07-26, finding 1 — a bare `except
            # Exception: pass` here previously swallowed this KeyError into a silent
            # `budget_estimate_micros = 0`, which reserves trivially and never bills). Loud
            # by construction: BudgetExhausted is a VrakshaError, so it propagates through
            # run_structured's `except VrakshaError: raise` unchanged, never mis-typed.
            log.error("budget anchor: no price for model %r -- blocking the call (fail-closed)", budget_model_id)
            raise BudgetExhausted(f"no price for model {budget_model_id!r}", ceiling="user", cause=exc) from exc
    try:
        result = await run_agent(
            handle._agent, user_prompt, deps=deps, usage_limits=limits,
            event_stream_handler=esh, message_history=history, model=model,
            budget_model_id=budget_model_id, budget_mission_id=budget_mission_id,
            budget_estimate_micros=budget_estimate_micros,
        )
    except VrakshaError:
        raise
    except UsageLimitExceeded as exc:
        raise MaxRetriesExceededError(
            f"{handle.layer} hit its turn/usage cap", cause=exc
        ) from exc
    except Exception as exc:
        raise ModelUnavailableError(
            f"{handle.layer} model call failed: {exc}",
            model=model_for_layer(handle.layer),
        ) from exc
    return result.output
