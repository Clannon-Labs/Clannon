"""
Per-dependency health probes for the /ready endpoint.
No user or tenant data flows through any function here.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3

log = logging.getLogger(__name__)


async def probe_qdrant() -> str:
    """'up' | 'down'. Fast circuit-breaker check first; live ping only when breaker is closed."""
    try:
        from core.memory import store as _store

        if _store.is_down():
            return "down"
        ok = await asyncio.to_thread(_store.healthcheck)
        return "up" if ok else "down"
    except Exception as exc:  # noqa: BLE001
        log.debug("qdrant probe error: %s", exc)
        return "down"


def probe_embeddings() -> str:
    """'up' | 'down'. Reads the loaded flag without triggering a model load."""
    try:
        from core.memory.embeddings import is_ready

        return "up" if is_ready() else "down"
    except Exception as exc:  # noqa: BLE001
        log.debug("embeddings probe error: %s", exc)
        return "down"


def probe_db() -> str:
    """'up' | 'down'. Minimal SQLite round-trip; no rows read, no user data."""
    try:
        from . import config

        conn = sqlite3.connect(config.DB_PATH, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        return "up"
    except Exception as exc:  # noqa: BLE001
        log.debug("db probe error: %s", exc)
        return "down"
