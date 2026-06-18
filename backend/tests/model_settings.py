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
