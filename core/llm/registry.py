"""Resolve Vraksha model profiles into Pydantic AI runtime settings."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from foundation import constants
from registry.config import ModelProfile, load_model_registry

# Per-request model overrides (role -> "provider:model"), set by the
# delivery layer (web server) from the requesting user's preferences.
# A ContextVar scopes the override to one asyncio task tree, so
# concurrent runs by different users never see each other's choices.
_MODEL_OVERRIDES: ContextVar[dict[str, str]] = ContextVar("vraksha_model_overrides", default={})


@contextmanager
def model_overrides(overrides: dict[str, str]) -> Iterator[None]:
    """Apply per-run model overrides for the duration of a pipeline run."""
    token = _MODEL_OVERRIDES.set(dict(overrides))
    try:
        yield
    finally:
        _MODEL_OVERRIDES.reset(token)


def model_profile_for_layer(layer: str) -> ModelProfile:
    """Return the configured model profile for a pipeline layer."""
    return load_model_registry().for_layer(layer)


def model_name_for_layer(layer: str) -> str:
    """
    Return a Pydantic AI model string for the layer.

    Pydantic AI accepts provider-qualified strings such as
    ``openai:gpt-5.2-mini``. Keeping this mapping here prevents verifier,
    filter, and orchestrator code from depending on provider naming details.
    A per-run override (user preference) wins over models.yaml.
    """
    override = _MODEL_OVERRIDES.get().get(layer)
    if override:
        return override
    profile = model_profile_for_layer(layer)
    return f"{profile.provider}:{profile.model}"


# Which env var proves a provider is usable. Chain entries for providers
# without a key are skipped instead of crashing the agent build.
_PROVIDER_KEY_ENVS: dict[str, tuple[str, ...]] = {
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def _google_api_keys() -> list[str]:
    """
    Every configured Google key, in priority order: GOOGLE_API_KEY (or
    GEMINI_API_KEY), then GOOGLE_API_KEY_2, _3, ... (contiguous numbering —
    a gap stops the scan). Keys from separate accounts carry separate free-tier
    quotas, so each becomes its own fallback entry: quota exhaustion on one
    account rotates to the next instead of failing the run.
    """
    import os

    keys: list[str] = []
    primary = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if primary:
        keys.append(primary)
    n = 2
    while key := os.getenv(f"GOOGLE_API_KEY_{n}"):
        keys.append(key)
        n += 1
    return keys


def _provider_available(model_string: str) -> bool:
    import os

    provider = model_string.split(":", 1)[0]
    if provider == "google":
        return bool(_google_api_keys())
    env_names = _PROVIDER_KEY_ENVS.get(provider)
    if env_names is None:
        return True  # unknown provider — let pydantic-ai decide
    return any(os.getenv(name) for name in env_names)


def _expand_keys(model_string: str) -> list[Any]:
    """
    One runnable entry per Google API key for google models (explicit
    per-key providers); everything else passes through as the plain
    provider-qualified string.
    """
    provider, _, name = model_string.partition(":")
    if provider != "google":
        return [model_string]
    keys = _google_api_keys()
    if len(keys) <= 1:
        return [model_string]
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    return [GoogleModel(name, provider=GoogleProvider(api_key=key)) for key in keys]


def fallback_chain_for_layer(layer: str) -> list[str]:
    """
    The layer's quota-resilience chain from models.yaml `fallbacks:`,
    filtered to providers whose API keys are actually configured.
    """
    config = load_model_registry().config
    chains = config.get("fallbacks") or {}
    chain = chains.get(layer) or []
    return [str(model) for model in chain if _provider_available(str(model))]


def model_for_layer(layer: str) -> str | FallbackModel:
    """
    Resolve the runnable model for a layer: the primary (override or
    models.yaml) backed by the layer's fallback chain. Any model API
    error — 429 quota, 503 overload, 404 retired id — moves to the next
    model in the chain, so one provider/model outage or quota never
    takes a run down with it.
    """
    primary = model_name_for_layer(layer)
    chain = [model for model in fallback_chain_for_layer(layer) if model != primary]
    if not _provider_available(primary) and chain:
        # the configured primary has no API key in this environment — promote the
        # first keyed chain entry instead of failing at FallbackModel build time
        primary, chain = chain[0], chain[1:]
    entries = _expand_keys(primary)
    for model in chain:
        entries.extend(_expand_keys(model))
    if len(entries) == 1:
        return entries[0]
    return FallbackModel(*entries)


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
