"""Resolve Vraksha model profiles into Pydantic AI runtime settings."""

from __future__ import annotations

from typing import Any

from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from foundation import ModelProfile, constants, load_model_registry


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


def usage_limits_for_layer(layer: str) -> UsageLimits:
    """
    Build conservative usage limits for structured stage agents.

    request_limit must allow the configured output-validation retries: each
    retry is a new model request, so the cap is retries + 1. A flat cap of 1
    would make the first malformed-output retry exceed the limit and turn a
    transient formatting hiccup into a hard failure.
    """
    if layer == "verifier":
        return UsageLimits(
            request_limit=constants.VERIFIER_MAX_RETRIES + 1,
            output_tokens_limit=constants.VERIFIER_MAX_TOKENS,
        )

    return UsageLimits(request_limit=1)
