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

from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, TypeVar

from pydantic_ai import Agent, FunctionToolCallEvent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded

from foundation import MaxRetriesExceededError, ModelUnavailableError, VrakshaError
from registry.config import get_prompt

from .registry import model_for_layer, model_settings_for_layer, usage_limits_for_layer
from .retry import run_agent

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


async def run_structured(
    handle: AgentHandle[T],
    prompt: str,
    *,
    deps: Any | None = None,
    max_turns: int | None = None,
    max_output_tokens: int | None = None,
    on_tool_event: Callable[[dict], Awaitable[None]] | None = None,
    model: Any | None = None,
) -> T:
    """
    Run an agent and return its validated structured output.

    Adds the shared transient-retry wrapper and per-layer usage limits. `max_turns`
    / `max_output_tokens` are neutral per-run overrides (the SDK `UsageLimits` is
    built here, so callers never import it). `on_tool_event` streams a live decision
    log; `model` overrides the model for this run only (tests inject a TestModel/
    FunctionModel). Foundation errors propagate unchanged; a usage/turn-cap breach
    becomes `MaxRetriesExceededError` (fail closed at the cap); any other
    framework/provider failure becomes `ModelUnavailableError`.
    """
    limits = usage_limits_for_layer(handle.layer, max_turns=max_turns, max_output_tokens=max_output_tokens)
    esh = _event_handler(on_tool_event) if on_tool_event is not None else None
    try:
        if model is not None:
            with handle._agent.override(model=model):
                result = await run_agent(
                    handle._agent, prompt, deps=deps, usage_limits=limits, event_stream_handler=esh
                )
        else:
            result = await run_agent(
                handle._agent, prompt, deps=deps, usage_limits=limits, event_stream_handler=esh
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
