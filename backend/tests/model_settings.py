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
    # reasoning roles default to Claude (best-for-task), NOT a hardcoded Gemini
    for role in ("orchestrator", "research", "planner", "code"):
        assert by_role[role]["default"].startswith("claude-"), f"{role} default should be Claude"
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


def test_parse_session_models_rejects_bad_input():
    with pytest.raises(HTTPException):       # not JSON
        _parse_session_models("not json")
    with pytest.raises(HTTPException):       # not an object
        _parse_session_models('["claude-opus-4-8"]')
    with pytest.raises(HTTPException):       # locked role
        _parse_session_models('{"verifier": "claude-haiku-4-5"}')
    with pytest.raises(HTTPException):       # unknown role
        _parse_session_models('{"nope": "claude-opus-4-8"}')
    with pytest.raises(HTTPException):       # model not offered for the role
        _parse_session_models('{"orchestrator": "not-a-real-model"}')
    with pytest.raises(HTTPException):       # text model on the media role
        _parse_session_models('{"media_expert": "claude-haiku-4-5"}')


# ---- resilience: media + code now have cross-provider fallback chains -------


def test_media_and_code_have_fallback_chains():
    chains = load_model_registry().config.get("fallbacks") or {}
    # the gap that made a rate-limited Gemini kill a media run is closed
    assert len(chains.get("media_expert") or []) >= 2
    assert len(chains.get("code") or []) >= 2
    # the media chain crosses providers so image/pdf survive Google being down
    providers = {entry.split(":", 1)[0] for entry in chains["media_expert"]}
    assert {"google", "openai", "anthropic"} <= providers
