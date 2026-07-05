"""
config — THE OWNER'S CONTROL PANEL for the product's business values.

ONE central, private place to change any business-side value of the product: plans,
pricing, tiers, feature flags, product limits, and the user-selectable model catalog.
Edit `config/business.yaml` — nothing else — to change a business value; the backend
reads it as authoritative and the frontend follows via `GET /config`, so the two never
drift.

Boundaries (LAW 4 — single-source, central, private):
  - Business values live HERE (this package).
  - Technical config (timeouts, hop/size caps) lives in `foundation/`.
  - Deployment/ops config (CORS, cookies, DB path, rate limits) stays with its layer
    (`api/config.py`), env-driven.
  - `api/` never exposes this file's raw contents — `GET /config` returns only the
    specific values a client legitimately needs.

This module just loads + exposes `business.yaml`; it holds NO config values of its own
(one source of truth — the YAML).
"""
from __future__ import annotations

from pathlib import Path

import yaml

_BUSINESS: dict = yaml.safe_load(
    (Path(__file__).parent / "business.yaml").read_text(encoding="utf-8")
)

# --- plans / pricing / features ------------------------------------------------
PLANS: list[dict] = _BUSINESS["plans"]
FEATURES: dict = _BUSINESS["features"]
DEFAULT_PLAN: str = _BUSINESS["default_plan"]   # new-signup default; api/ applies any env override

# --- product limits (server-enforced; mirrored to the UI via /config so it can't drift) ---
_LIM: dict = _BUSINESS["limits"]
BRIEF_MIN_CHARS: int = _LIM["briefMinChars"]
BRIEF_MAX_CHARS: int = _LIM["briefMaxChars"]
MAX_INPUT_FILES: int = _LIM["maxInputFiles"]
WIKI_UPLOAD_MAX_FILES: int = _LIM["wikiUploadMaxFiles"]
WIKI_UPLOAD_MAX_BYTES: int = _LIM["wikiUploadMaxBytes"]
WIKI_UPLOAD_EXTENSIONS: tuple[str, ...] = tuple(_LIM["wikiUploadExtensions"])
# The /config.limits payload shape (camelCase, matching the frontend contract).
LIMITS: dict = {
    "briefMinChars": BRIEF_MIN_CHARS,
    "briefMaxChars": BRIEF_MAX_CHARS,
    "maxInputFiles": MAX_INPUT_FILES,
    "wikiUploadMaxFiles": WIKI_UPLOAD_MAX_FILES,
    "wikiUploadMaxBytes": WIKI_UPLOAD_MAX_BYTES,
    "wikiUploadExtensions": list(WIKI_UPLOAD_EXTENSIONS),
}

# --- user-selectable model catalog (what Settings → Models offers) -------------
SELECTABLE_MODELS: list[str] = _BUSINESS["selectable_models"]
MEDIA_MODELS: list[str] = _BUSINESS["media_models"]

__all__ = [
    "PLANS", "FEATURES", "DEFAULT_PLAN",
    "LIMITS", "BRIEF_MIN_CHARS", "BRIEF_MAX_CHARS", "MAX_INPUT_FILES",
    "WIKI_UPLOAD_MAX_FILES", "WIKI_UPLOAD_MAX_BYTES", "WIKI_UPLOAD_EXTENSIONS",
    "SELECTABLE_MODELS", "MEDIA_MODELS",
]
