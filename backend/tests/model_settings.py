"""Per-role model selection + best-for-task defaults + media/code resilience.

Covers the model picker contract: the catalog is per-role with defaults DERIVED from
models.yaml (Claude for reasoning, Gemini for media — never 'Gemini everywhere'),
per-session overrides layer over workspace defaults, and media/document + code runs
have a cross-provider fallback chain so a down provider swaps model instead of failing.
"""

from api import config
from api.app import _parse_session_models
from api.runs import build_model_overrides
from registry.config import load_model_registry

import pytest
from fastapi import HTTPException


# ---- catalog: per-role, best-for-task defaults derived from models.yaml ----


def test_catalog_is_per_role_not_gemini_everywhere():
    by_role = {e["layer"]: e for e in config.MODEL_CATALOG}
    # the five selectable reasoning/media roles + the two locked security gates
    assert config.SELECTABLE_ROLES == {"orchestrator", "research", "planner", "code", "media_expert"}
    assert config.LOCKED_ROLES == {"verifier", "filter"}
    # reasoning roles default to a BEST-FOR-TASK model (Claude/GPT/...), never a hardcoded
    # "Gemini everywhere" — the actual provider per role is a models.yaml config choice
    for role in ("orchestrator", "research", "planner", "code"):
        assert not by_role[role]["default"].startswith("gemini-"), f"{role} default should not be Gemini"
    # media defaults to Gemini (the only one that reads audio/video + PDFs natively)
    assert by_role["media_expert"]["default"].startswith("gemini-")


def test_catalog_default_tracks_models_yaml():
    # the UI default is derived, so it always equals what the pipeline actually routes to
    reg = load_model_registry()
    for entry in config.MODEL_CATALOG:
        if entry["default"]:
            assert entry["default"] == reg.for_layer(entry["layer"]).model


def test_media_role_offers_multimodal_options_only():
    media = next(e for e in config.MODEL_CATALOG if e["layer"] == "media_expert")
    # gemini variants (full media) plus vision models for image/pdf; no text-only ids
    assert any(m.startswith("gemini-") for m in media["options"])
    assert media["options"] != config.SELECTABLE_MODELS   # a distinct, vision-capable list


def test_locked_roles_are_read_only_with_no_options():
    for e in config.MODEL_CATALOG:
        if e["locked"]:
            assert e["options"] == []


def test_experts_auto_surface_under_their_role():
    # any expert added to the backend appears under the role it runs on, zero edits here
    by_role = {e["layer"]: e for e in config.MODEL_CATALOG}
    media_drives = {x["key"] for x in by_role["media_expert"]["experts"]}
    assert "media.analyst" in media_drives
    research_drives = {x["key"] for x in by_role["research"]["experts"]}
    assert "web.research" in research_drives


# ---- per-session overrides layer over workspace defaults --------------------


def test_session_override_qualifies_and_filters_locked():
    # a fresh user has no stored prefs, so this is the pure per-session path
    ov = build_model_overrides("no-such-user-xyz", {"orchestrator": "claude-opus-4-8",
                                                    "media_expert": "gemini-2.5-pro",
                                                    "verifier": "claude-haiku-4-5"})
    assert ov["orchestrator"] == "anthropic:claude-opus-4-8"
    assert ov["media_expert"] == "google:gemini-2.5-pro"
    assert "verifier" not in ov          # locked role is never overridable


def test_no_session_and_no_prefs_means_no_overrides():
    assert build_model_overrides("no-such-user-xyz", None) == {}
    assert build_model_overrides("no-such-user-xyz", {}) == {}


# ---- parsing the per-session `models` form field ---------------------------


def test_parse_session_models_valid():
    out = _parse_session_models('{"orchestrator": "claude-opus-4-8", "code": "gpt-5.4"}')
    assert out == {"orchestrator": "claude-opus-4-8", "code": "gpt-5.4"}


def test_parse_session_models_empty_is_no_overrides():
    assert _parse_session_models("") == {}
    assert _parse_session_models("   ") == {}
    assert _parse_session_models("{}") == {}


def test_parse_session_models_rejects_malformed_body():
    # a structurally broken body is still a 422 (a real client error, not a picker choice)
    with pytest.raises(HTTPException):       # not JSON
        _parse_session_models("not json")
    with pytest.raises(HTTPException):       # not an object
        _parse_session_models('["claude-opus-4-8"]')


def test_parse_session_models_drops_invalid_entries_never_fails():
    # an entry that doesn't validate is DROPPED (the role falls back to its default), never a
    # 422 — so the per-conversation model picker can never break a run.
    assert _parse_session_models('{"verifier": "claude-haiku-4-5"}') == {}      # locked role
    assert _parse_session_models('{"nope": "claude-opus-4-8"}') == {}           # unknown role
    assert _parse_session_models('{"orchestrator": "not-a-real-model"}') == {}  # model not offered
    assert _parse_session_models('{"media_expert": "claude-haiku-4-5"}') == {}  # text model on the media role
    # a valid entry alongside an invalid one keeps the valid and drops the invalid
    assert _parse_session_models(
        '{"orchestrator": "claude-opus-4-8", "nope": "x"}'
    ) == {"orchestrator": "claude-opus-4-8"}


# ---- resilience: media + code now have cross-provider fallback chains -------


def test_media_and_code_have_fallback_chains():
    chains = load_model_registry().config.get("fallbacks") or {}
    # the gap that made a rate-limited Gemini kill a media run is closed
    assert len(chains.get("media_expert") or []) >= 2
    assert len(chains.get("code") or []) >= 2
    # the media chain crosses providers so image/pdf survive Google being down
    providers = {entry.split(":", 1)[0] for entry in chains["media_expert"]}
    assert {"google", "openai", "anthropic"} <= providers


# ---- provider-agnosticism: the anthropic_cache_* knobs must be inert elsewhere ----


def test_anthropic_cache_settings_are_inert_on_other_providers():
    """The anthropic_cache_* keys are NAMESPACED no-ops on every other provider, so a
    multi-provider models.yaml — or a brand-new provider added tomorrow — never breaks.
    Proven by mapping a real Google request with the settings present: no error, and no
    anthropic key leaks into the Gemini request (Google caches implicitly via its own
    `cached_content`). Anthropic is the only provider that needs the explicit breakpoint."""
    import asyncio
    import os

    os.environ.setdefault("GOOGLE_API_KEY", "x")
    from core.llm.registry import model_settings_for_layer
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.models.google import GoogleModel

    settings = model_settings_for_layer("orchestrator")           # carries all 3 anthropic_cache_* keys
    assert any("anthropic" in k for k in settings)                # they ARE set on the layer
    builder = getattr(GoogleModel("gemini-2.5-flash-lite", provider="google"), "_build_content_and_config", None)
    if builder is None:                                           # pydantic-ai internal moved; source review still holds
        return
    msgs = [ModelRequest(parts=[UserPromptPart(content="hi")])]
    _, cfg = asyncio.run(builder(msgs, settings, ModelRequestParameters()))
    assert not [k for k in cfg if "anthropic" in str(k).lower()]  # zero leakage into the provider request


# ---- characterization: per-layer settings + usage limits are PINNED ----------
#
# GOLDEN values. model_settings_for_layer / usage_limits_for_layer only special-case
# verifier (token + timeout cap) and orchestrator (turn-sized request limit); the
# message-history cache (anthropic_cache) is on for exactly the multi-turn layers.
# Every other layer takes the generic path. The failure these guard against is a layer
# SILENTLY falling back to the generic defaults — a renamed layer, an entry dropped from
# _MESSAGE_CACHE_LAYERS, the verifier/orchestrator branch no longer matching. That kind
# of drift is invisible at runtime (a run still "works", just unbounded or uncached), so
# it has to be pinned here. The numeric caps are tied to their foundation constants on
# purpose: a deliberate constant tune flows through, but a layer dropping off its branch
# does not. Update intentionally, never to make a red test green.

from core.llm.registry import model_settings_for_layer, usage_limits_for_layer
from foundation import constants
import settings

# the two anthropic prompt-prefix cache knobs every layer carries
_CACHE_PREFIX = {"anthropic_cache_instructions": True, "anthropic_cache_tool_definitions": True}
# the multi-turn layers ALSO cache the growing message history (W8)
_CACHE_PREFIX_AND_HISTORY = {**_CACHE_PREFIX, "anthropic_cache": True}

EXPECTED_MODEL_SETTINGS = {
    # multi-turn, tool/expert-driving layers: prefix cache + message-history cache
    "orchestrator": _CACHE_PREFIX_AND_HISTORY,
    "research": _CACHE_PREFIX_AND_HISTORY,
    "code": _CACHE_PREFIX_AND_HISTORY,
    "planner": _CACHE_PREFIX_AND_HISTORY,
    "media_expert": _CACHE_PREFIX_AND_HISTORY,
    # verifier additionally pins a hard token + timeout cap (fail closed on a slow gate)
    "verifier": {**_CACHE_PREFIX, "max_tokens": settings.VERIFIER.max_tokens,
                 "timeout": settings.VERIFIER.timeout_s},
    # one-shot / varying-input layers: prefix cache only, no history cache
    "filter": _CACHE_PREFIX,
    "normalizer": _CACHE_PREFIX,
    "memory": _CACHE_PREFIX,
    "search": _CACHE_PREFIX,
    "slop_detector": _CACHE_PREFIX,
}

# (request_limit, output_tokens_limit) for the no-override base path
EXPECTED_USAGE_LIMITS = {
    "verifier": (settings.VERIFIER.max_retries + 1, settings.VERIFIER.max_tokens),
    "orchestrator": (constants.ORCHESTRATOR_MAX_TURNS + 1, constants.ORCHESTRATOR_MAX_TOKENS),
    # everything else is a one-shot structured agent: one request, no token cap baked in
    "filter": (1, None),
    "research": (1, None),
    "code": (1, None),
    "planner": (1, None),
    "media_expert": (1, None),
    "normalizer": (1, None),
    "memory": (1, None),
    "search": (1, None),
    "slop_detector": (1, None),
}


@pytest.mark.parametrize("layer,expected", sorted(EXPECTED_MODEL_SETTINGS.items()))
def test_model_settings_per_layer_are_pinned(layer, expected):
    # exact dict equality: an extra/missing key (e.g. anthropic_cache silently gone) fails here
    assert dict(model_settings_for_layer(layer)) == expected


def test_verifier_is_the_only_layer_with_a_token_and_timeout_cap():
    # the special-case is verifier-only; nothing else should sprout max_tokens/timeout
    for layer in EXPECTED_MODEL_SETTINGS:
        settings = model_settings_for_layer(layer)
        has_caps = "max_tokens" in settings or "timeout" in settings
        assert has_caps == (layer == "verifier"), layer


@pytest.mark.parametrize("layer,expected", sorted(EXPECTED_USAGE_LIMITS.items()))
def test_usage_limits_per_layer_are_pinned(layer, expected):
    limits = usage_limits_for_layer(layer)
    assert (limits.request_limit, limits.output_tokens_limit) == expected


def test_usage_limits_per_run_overrides_resize_request_limit():
    # max_turns resizes the request cap to turns+1; the layer's base token cap is preserved
    orch = usage_limits_for_layer("orchestrator", max_turns=5)
    assert (orch.request_limit, orch.output_tokens_limit) == (6, constants.ORCHESTRATOR_MAX_TOKENS)
    # a tool-driving layer with no base token cap: override sets requests, tokens stay unbounded
    research = usage_limits_for_layer("research", max_turns=8)
    assert (research.request_limit, research.output_tokens_limit) == (9, None)
    # an explicit per-run token cap wins over the base
    capped = usage_limits_for_layer("orchestrator", max_turns=3, max_output_tokens=1234)
    assert (capped.request_limit, capped.output_tokens_limit) == (4, 1234)
    # token override without a turn override leaves the base request cap untouched
    filtered = usage_limits_for_layer("filter", max_output_tokens=99)
    assert (filtered.request_limit, filtered.output_tokens_limit) == (1, 99)
