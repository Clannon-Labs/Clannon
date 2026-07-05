"""
api/ deployment + runtime config, plus assembly of the GET /config payload.

BUSINESS values (plans, pricing, features, product limits, the user-selectable model
catalog) live in the central `config/` control panel (LAW 4 — one central, private
source) and are imported below — this file no longer defines them. What stays here is
DEPLOYMENT/ops config (CORS, cookies, DB path, request-size + auth rate limits), which
is env-driven and changes per environment, not per product decision.
"""

from __future__ import annotations

import os

# Business values — the owner's control panel (config/business.yaml). Imported here so
# api/ (and the /config payload) read the single source, never a private duplicate.
from config import (
    PLANS,
    FEATURES,
    LIMITS,
    BRIEF_MIN_CHARS,
    BRIEF_MAX_CHARS,
    MAX_INPUT_FILES,
    WIKI_UPLOAD_MAX_FILES,
    WIKI_UPLOAD_MAX_BYTES,
    WIKI_UPLOAD_EXTENSIONS,
    SELECTABLE_MODELS,
    MEDIA_MODELS,
    DEFAULT_PLAN as _BUSINESS_DEFAULT_PLAN,
)

VERSION = "0.1-dev"

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
# Origins allowed to call the API with credentials (the session cookie). Comma-
# separated; defaults to the single FRONTEND_ORIGIN, so dev is unchanged. In
# production set e.g. "https://clannon.com,https://app.clannon.com" so both the
# marketing apex and the workspace subdomain can make authenticated XHR/SSE calls.
CORS_ORIGINS = [
    o.strip() for o in os.getenv("SERVER_CORS_ORIGINS", FRONTEND_ORIGIN).split(",") if o.strip()
]
# Plan assigned to new signups — the business default (config/business.yaml), with a
# deployment env override (SERVER_DEFAULT_PLAN) for e.g. "pro" in local dev.
DEFAULT_PLAN = os.getenv("SERVER_DEFAULT_PLAN") or _BUSINESS_DEFAULT_PLAN
COOKIE_NAME = "clannon_session"
COOKIE_SECURE = os.getenv("SERVER_COOKIE_SECURE", "0") == "1"
# Cookie domain. Unset (default) → a host-only cookie (today's same-origin dev
# behavior). Set to ".clannon.com" in production so ONE session cookie is valid for
# the apex AND every subdomain (clannon.com ↔ app.clannon.com) — that is the whole
# mechanism behind seamless, no-relogin auth when the workspace moves to app.clannon.com.
COOKIE_DOMAIN = os.getenv("SERVER_COOKIE_DOMAIN") or None
SESSION_TTL_S = 60 * 60 * 24 * 14  # 14 days
DB_PATH = os.getenv("SERVER_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "clannon.db"))

# PLANS + FEATURES are imported from config/ (the owner's control panel) above —
# defined once in config/business.yaml, served here via /config.

# Product input limits (BRIEF_*, MAX_INPUT_FILES, WIKI_UPLOAD_*, and the LIMITS payload)
# are imported from config/ above — server-enforced here, surfaced to the UI via
# /config.limits so the client validates against the exact numbers the server enforces.

# Transport-layer body-size ceiling enforced by hardening.BodySizeLimitMiddleware BEFORE
# any route or pipeline stage runs.  Must exceed any legitimate payload: the largest
# upload is WIKI_UPLOAD_MAX_BYTES × WIKI_UPLOAD_MAX_FILES = 5 MB plus multipart overhead.
# 32 MB is generous for the current feature set and low enough to stop a memory-overload
# attack at the edge.  Override at deployment with MAX_REQUEST_BODY_BYTES env var.
MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(32 * 1024 * 1024)))

# Auth rate limit on credential endpoints (server-side only — not UI-relevant).
AUTH_RATE_WINDOW_S = 60
AUTH_RATE_MAX_ATTEMPTS = 10

# The user-selectable model catalog (SELECTABLE_MODELS text/reasoning + MEDIA_MODELS
# multimodal) is imported from config/ above — curating what users can pick is a business
# decision, so it lives in config/business.yaml.
#
# SECURITY note (unchanged): the verifier + output-filter layers are system-managed and
# NOT user-selectable — users must never swap in a weaker model and degrade their own
# input/output gates. The API rejects writes to those locked layers with 403; the UI shows
# them read-only. The actual model each layer runs comes from models.yaml.


def qualify_model(model_id: str) -> str:
    """Map a bare catalog id to pydantic-ai's provider-qualified form."""
    if model_id.startswith("gemini-"):
        return f"google:{model_id}"
    if model_id.startswith("claude-"):
        return f"anthropic:{model_id}"
    if model_id.startswith("gpt-"):
        return f"openai:{model_id}"
    return model_id


def _discover_experts() -> list[dict]:
    """Every registered, healthy expert as {key, label, role}, from the registry. The
    model-settings UI groups these UNDER their role, so any expert added to the backend
    auto-appears under the role it runs on, with zero edits here."""
    from registry.capabilities import CapabilityKind, discover, registry

    discover()
    broken = {b.key for b in registry.broken()}
    out: list[dict] = []
    for card in registry.cards(CapabilityKind.EXPERT):
        key = card["key"]
        if key in broken:
            continue
        spec = registry.get_expert(key)
        out.append({
            "key": key,
            "label": card["label"],   # one canonical label from the registry (was ad-hoc _expert_label)
            "role": getattr(spec, "model_role", None) or "research",
        })
    return sorted(out, key=lambda e: e["key"])


EXPERTS = _discover_experts()


def _role_default(role: str) -> str:
    """The bare model id models.yaml routes this role to by default, so the picker's
    default selection always matches what the pipeline actually runs (best-for-task
    there: Claude for reasoning, Gemini for media) — never a hardcoded provider."""
    from core.llm.registry import model_profile_for_layer

    try:
        return model_profile_for_layer(role).model
    except Exception:  # noqa: BLE001 — a role models.yaml doesn't define has no default to show
        return ""


# The roles a user can see/configure, each a models.yaml role: (layer, label,
# description, locked, options). locked=True = security gate (verifier, output filter):
# system-managed, shown read-only, 403 on write — users must never swap a weaker model
# into their own input/output guards. The default is DERIVED from models.yaml so the UI
# stays in lockstep with routing.
_ROLES = [
    ("orchestrator", "Orchestrator", "Plans the run, routes experts, streams the decision log.", False, SELECTABLE_MODELS),
    ("research", "Research", "Web research, fact-checking, and summarizing sources.", False, SELECTABLE_MODELS),
    ("planner", "Writing & planning", "Synthesis, documentation, and long-form reasoning.", False, SELECTABLE_MODELS),
    ("code", "Code & data", "Code generation, debugging, and data analysis.", False, SELECTABLE_MODELS),
    ("media_expert", "Media & documents", "Images, audio, video, and PDF documents.", False, MEDIA_MODELS),
    ("verifier", "Verifier", "Security gate on every input. System-managed, not a preference.", True, []),
    ("filter", "Output filter", "Groundedness and policy gate on every report. System-managed.", True, []),
]


def model_catalog() -> list[dict]:
    """Per-role catalog: label, options, locked, default (derived from models.yaml),
    and the experts each role drives (informational, so the UI can explain the mapping)."""
    return [
        {
            "layer": layer,
            "label": label,
            "description": desc,
            "locked": locked,
            "default": _role_default(layer),
            "options": list(options),
            "experts": [
                {"key": e["key"], "label": e["label"]} for e in EXPERTS if e["role"] == layer
            ],
        }
        for layer, label, desc, locked, options in _ROLES
    ]


MODEL_CATALOG = model_catalog()
# Roles a workspace default / per-session override may target (unlocked only).
SELECTABLE_ROLES = {layer for layer, _l, _d, locked, _o in _ROLES if not locked}
LOCKED_ROLES = {layer for layer, _l, _d, locked, _o in _ROLES if locked}


def remote_config() -> dict:
    return {
        "version": VERSION,
        "plans": PLANS,
        "features": FEATURES,
        "limits": LIMITS,
    }
