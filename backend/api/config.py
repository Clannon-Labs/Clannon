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

# User-selectable pool for the reasoning layers (orchestrator, experts).
SELECTABLE_MODELS = [
    # Google (default provider)
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

# Experts users can override individually (key = capability name shown in
# the UI; role = the models.yaml role that expert resolves through).
EXPERTS = [
    {"key": "web.research", "label": "Web research", "role": "research"},
    {"key": "synthesis.writer", "label": "Synthesis writer", "role": "planner"},
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


MODEL_CATALOG = [
    # {
    #     "layer": "verifier",
    #     "label": "Verifier",
    #     "description": "Security gate on every input. System-managed — this is part of the pipeline's safety guarantee, not a preference.",
    #     "locked": True,
    #     "default": "gemini-2.5-flash-lite",
    #     "options": [],
    # },
    {
        "layer": "orchestrator",
        "label": "Orchestrator",
        "description": "Plans the run, routes experts, streams the decision log.",
        "locked": False,
        "default": "gemini-3.1-flash-lite",
        "options": SELECTABLE_MODELS,
    },
    {
        "layer": "experts",
        "label": "Experts",
        "description": "Research and synthesis workers.",
        "locked": False,
        "default": "gemini-3.1-flash-lite",
        "options": SELECTABLE_MODELS,
    },
    # {
    #     "layer": "filter",
    #     "label": "Output filter",
    #     "description": "Groundedness and policy gate on every report. System-managed for the same reason as the verifier.",
    #     "locked": True,
    #     "default": "gemini-2.5-flash-lite",
    #     "options": [],
    # },
]


def remote_config() -> dict:
    return {
        "version": VERSION,
        "plans": PLANS,
        "features": FEATURES,
        "limits": LIMITS,
    }
