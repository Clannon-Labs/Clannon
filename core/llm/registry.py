"""Resolve Vraksha model profiles into Pydantic AI runtime settings."""

from __future__ import annotations

from typing import Any

from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from foundation import constants
from registry.config import ModelProfile, load_model_registry


def model_profile_for_layer(layer: str) -> ModelProfile:
    """Return the configured model profile for a pipeline layer."""
    return load_model_registry().for_layer(layer)


def model_name_for_layer(layer: str) -> str:
    """
    Return a Pydantic AI model string for the layer.

    Pydantic AI accepts provider-qualified strings such as
    ``openai:gpt-5.2-mini``. Keeping this mapping here prevents verifier,
    filter, and orchestrator code from depending on provider naming details.
    """
    profile = model_profile_for_layer(layer)
    return f"{profile.provider}:{profile.model}"


def model_settings_for_layer(layer: str) -> ModelSettings:
    """Build bounded model settings for a pipeline layer."""
    profile = model_profile_for_layer(layer)
    settings: dict[str, Any] = dict(profile.settings)

    if layer == "verifier":
        settings.setdefault("max_tokens", constants.VERIFIER_MAX_TOKENS)
        settings.setdefault("timeout", constants.VERIFIER_TIMEOUT_S)

    return ModelSettings(**settings)


def usage_limits_for_layer(
    layer: str,
    *,
    max_turns: int | None = None,
    max_output_tokens: int | None = None,
) -> UsageLimits:
    """
    Build usage limits for a stage agent.

    `request_limit` caps model requests in one run. A one-shot structured agent
    (verifier, filter) needs retries + 1 (each malformed-output retry is a request);
    a tool-driving agent (orchestrator, experts) needs one request per tool round
    plus the final answer, so it is sized by a turn cap. `max_turns` /
    `max_output_tokens` are optional PER-RUN overrides (temporary, this run only):
    `request_limit` becomes `max_turns + 1` (turns + final answer). Callers pass
    plain ints; this is the single place the SDK `UsageLimits` is built.
    """
    if layer == "verifier":
        base_requests = constants.VERIFIER_MAX_RETRIES + 1
        base_tokens: int | None = constants.VERIFIER_MAX_TOKENS
    elif layer == "orchestrator":
        base_requests = constants.ORCHESTRATOR_MAX_TURNS + 1
        base_tokens = constants.ORCHESTRATOR_MAX_TOKENS
    else:
        # one-shot structured agents (e.g. filter); tool-driving callers override.
        base_requests = 1
        base_tokens = None

    request_limit = (max_turns + 1) if max_turns is not None else base_requests
    output_tokens_limit = max_output_tokens if max_output_tokens is not None else base_tokens

    if output_tokens_limit is None:
        return UsageLimits(request_limit=request_limit)
    return UsageLimits(request_limit=request_limit, output_tokens_limit=output_tokens_limit)
