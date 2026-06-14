"""
Server configuration — the read-only payload served at GET /config plus
server runtime settings. The frontend treats whatever this returns as
authoritative over its local defaults (plans, features, limits), so this
file is the single place pricing/budget display values live backend-side.
"""

from __future__ import annotations

import os

VERSION = "0.1-dev"

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
# Plan assigned to new signups. "pro" is handy in local dev (unlocks all
# memory tiers); production keeps "free" until Stripe drives upgrades.
DEFAULT_PLAN = os.getenv("SERVER_DEFAULT_PLAN", "free")
COOKIE_NAME = "clannon_session"
COOKIE_SECURE = os.getenv("SERVER_COOKIE_SECURE", "0") == "1"
SESSION_TTL_S = 60 * 60 * 24 * 14  # 14 days
DB_PATH = os.getenv("SERVER_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "clannon.db"))

# Mirrors clannon/frontend/src/config/plans.ts — served via /config so the
# frontend never drifts from what the backend believes.
PLANS = [
    {
        "id": "free",
        "name": "Seedling",
        "monthlyUsd": 0,
        "tokenBudget": 100_000,
        "tagline": "Feel the continuity. Three real runs a month.",
        "memoryTiers": ["episodic"],
        "features": [
            "100k tokens / month",
            "Single research workflow",
            "Community support",
        ],
    },
    {
        "id": "starter",
        "name": "Starter",
        "monthlyUsd": 29,
        "tokenBudget": 2_000_000,
        "tagline": "For the freelancer with recurring clients.",
        "memoryTiers": ["episodic", "wiki"],
        "features": [
            "2M tokens / month",
            "Episodic + Wiki memory",
            "Editable client wiki — your facts outrank inference",
            "All research workflows",
            "Email delivery",
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "monthlyUsd": 79,
        "tokenBudget": 6_000_000,
        "tagline": "The full memory system. This is where it compounds.",
        "memoryTiers": ["episodic", "wiki", "semantic", "procedural"],
        "features": [
            "6M tokens / month",
            "All four memory tiers",
            "Semantic graph — facts, sources, provenance",
            "Procedural memory — it learns how you work",
            "Per-layer model configuration",
            "Priority queue",
        ],
        "highlight": True,
    },
    {
        "id": "agency",
        "name": "Agency",
        "monthlyUsd": 199,
        "tokenBudget": 20_000_000,
        "tagline": "Every client, every project, one growing archive.",
        "memoryTiers": ["episodic", "wiki", "semantic", "procedural"],
        "features": [
            "20M tokens / month",
            "All four memory tiers",
            "Unlimited client workspaces",
            "MCP integrations — context flows in automatically",
            "Team seats (up to 5)",
            "Dedicated support",
        ],
    },
]

FEATURES = {"demo": True, "billing": True}
# low floor on purpose: a message can be as short as "hi" — the workspace is a
# conversation, not a form. The pipeline handles short and long inputs alike.
LIMITS = {"briefMinChars": 2}

# ---------------------------------------------------------------------------
# Model catalog — the single backend-editable source for what users see in
# Settings → Models. Verified against provider docs June 2026.
#
# locked=True marks SECURITY layers (verifier, output filter): the models
# guarding the pipeline are system-managed — users must never be able to
# swap in a weaker model and degrade their own input/output gates. The
# API rejects writes to locked layers with 403; the UI shows them
# read-only. The actual model the pipeline uses comes from models.yaml.
# ---------------------------------------------------------------------------

# User-selectable text/reasoning models (orchestrator, research, planning, code).
SELECTABLE_MODELS = [
    # Google
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    # Anthropic
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    # OpenAI
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
]

# Media/document understanding needs MULTIMODAL models. Gemini reads everything
# (image/audio/video/PDF); the cross-provider vision models cover image + PDF. Audio
# and video need Gemini, so it leads the list.
MEDIA_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.5-flash",
    "gemini-2.5-flash-lite",
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "gpt-5.4",
]


def qualify_model(model_id: str) -> str:
    """Map a bare catalog id to pydantic-ai's provider-qualified form."""
    if model_id.startswith("gemini-"):
        return f"google:{model_id}"
    if model_id.startswith("claude-"):
        return f"anthropic:{model_id}"
    if model_id.startswith("gpt-"):
        return f"openai:{model_id}"
    return model_id


def _expert_label(key: str) -> str:
    """A readable display name from a capability key, e.g. 'media.analyst' -> 'Media analyst'."""
    return key.replace(".", " ").replace("_", " ").capitalize()


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
            "label": _expert_label(key),
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
