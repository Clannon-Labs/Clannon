"""
The single boundary to the LLM framework (PydanticAI).

This is the ONLY module in Vraksha that imports `pydantic_ai`. Every stage that
needs a structured LLM call (verifier, orchestrator advisor, future output
filter) goes through `build_agent` + `run_structured` here. To swap or audit the
framework, you edit this one file — no other module touches the SDK.

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

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, TypeVar

from pydantic_ai import Agent

from foundation import ModelUnavailableError, VrakshaError, get_prompt

from .registry import model_name_for_layer, model_settings_for_layer, usage_limits_for_layer
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
        model_name_for_layer(layer),
        output_type=output_type,
        system_prompt=get_prompt(prompt_name).text,
        model_settings=model_settings_for_layer(layer),
        retries=retries,
        defer_model_check=True,
    )
    return AgentHandle(agent, layer)


async def run_structured(
    handle: AgentHandle[T],
    prompt: str,
    *,
    deps: Any | None = None,
    usage_limits: Any | None = None,
) -> T:
    """
    Run an agent and return its validated structured output.

    Adds the shared transient-retry wrapper and per-layer usage limits. Foundation
    errors (e.g. ConfigError, a stage's own VrakshaError) propagate unchanged; any
    other framework/provider failure is translated to ModelUnavailableError so
    callers fail closed on a clear, layer-tagged error.
    """
    limits = usage_limits if usage_limits is not None else usage_limits_for_layer(handle.layer)
    try:
        result = await run_agent(handle._agent, prompt, deps=deps, usage_limits=limits)
    except VrakshaError:
        raise
    except Exception as exc:
        raise ModelUnavailableError(
            f"{handle.layer} model call failed: {exc}",
            model=model_name_for_layer(handle.layer),
        ) from exc
    return result.output
