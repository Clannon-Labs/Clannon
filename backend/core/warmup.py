"""
Startup warmup — load the heavy, lazily-initialised resources once, up front, so
the FIRST real turn doesn't pay their cold start.

Three things dominate first-turn latency and the "memory wasn't available" symptom:
  * the embedding model (~500MB, downloaded/loaded on first use),
  * the Qdrant connection (lazy client + circuit breaker),
  * the Presidio/spaCy engines the text sanitizer uses.

`warmup()` triggers all three concurrently, off the event loop. It is BEST-EFFORT
and NON-BLOCKING by contract: a warmup failure is logged and ignored — the lazy
paths still load (and degrade) on demand, so warmup can never fail or slow a run.
Call it fire-and-forget at process startup (CLI/TUI and the API server).
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def _warm_embeddings() -> None:
    try:
        from core.memory import embeddings

        ok = await embeddings.warm()
        log.info("warmup: embeddings %s", "ready" if ok else "unavailable (will retry lazily)")
    except Exception as exc:  # noqa: BLE001 — warmup never affects a run
        log.warning("warmup: embeddings skipped: %s", exc)


async def _warm_qdrant() -> None:
    try:
        from core.memory import store

        ok = await asyncio.to_thread(store.healthcheck)
        log.info("warmup: qdrant %s", "ready" if ok else "down/disabled (will retry lazily)")
    except Exception as exc:  # noqa: BLE001
        log.warning("warmup: qdrant skipped: %s", exc)


async def _warm_sanitizer() -> None:
    try:
        from security.sanitizers.workers import text as text_worker

        ok = await asyncio.to_thread(text_worker.warm)
        log.info("warmup: sanitizer %s", "ready" if ok else "unavailable (will build lazily)")
    except Exception as exc:  # noqa: BLE001
        log.warning("warmup: sanitizer skipped: %s", exc)


async def warmup() -> None:
    """Warm embeddings + Qdrant + the text sanitizer concurrently. Best-effort."""
    await asyncio.gather(_warm_embeddings(), _warm_qdrant(), _warm_sanitizer())
