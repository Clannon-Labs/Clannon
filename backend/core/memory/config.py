"""
core/memory/config.py

Every environment-variable-driven setting this module reads, in ONE place
(LAW 1 — single source of truth; LAW 4 — one config file per concern).
`store.py` / `graph_store.py` / `embeddings.py` import from here instead of
each calling `os.getenv` themselves — to change any of these, this is the
one file to edit.

This consolidates core/memory's OWN scatter. Whether it should live under a
broader shared config/ folder alongside `models.yaml` and
`registry/config/` — the wider Law 4 question, since the same scatter exists
in ~20 other backend modules — is proposed separately
(`to-backend/2026-07-05_law4-config-scatter.md`), not decided here.
"""
from __future__ import annotations

import os

# --- vector tier (Qdrant) -----------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
MEMORY_DISABLED = os.getenv("VRAKSHA_MEMORY_DISABLED", "0") == "1"

# --- embeddings (fastembed) ----------------------------------------------
EMBED_CACHE_DIR = os.getenv("VRAKSHA_EMBED_CACHE")  # None = fastembed's own default

# --- graph tier (Kuzu) -----------------------------------------------------
GRAPH_DISABLED = os.getenv("VRAKSHA_GRAPH_DISABLED", "0") == "1"


def graph_db_path_override() -> str | None:
    """None = use the default path under core/memory/data/. A FUNCTION, not a
    frozen constant like the others above: graph_store re-derives its db path
    on every (re)connect (its lazy singleton gets reset far more often than
    the process — e.g. once per test), so this must re-read the env var each
    call rather than freeze whatever it was at first import."""
    return os.getenv("VRAKSHA_GRAPH_DB_PATH")
