"""
Embedding wrapper — fastembed nomic-embed-text-v1.5 (768 dims, local ONNX).

Lazy singleton: the model (~500MB on first download) loads on first use, off
the event loop. If it can't load, callers get None and degrade gracefully —
memory never takes a run down (ARCHITECTURE.md §6).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

log = logging.getLogger(__name__)

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
DIMS = 768

# A load failure is TRANSIENT, not terminal: a cold first call can stall or fail
# (the ~500MB download, a momentary disk/network hiccup). The old code latched
# `_failed = True` for the whole process — one bad first call disabled memory until
# restart. Instead, back off for _RETRY_AFTER_S and try again, exactly like the
# Qdrant breaker, so memory self-heals once the model is actually available.
_RETRY_AFTER_S = 60.0
_model = None
_retry_after = 0.0
_lock = threading.Lock()


def _load():
    global _model, _retry_after
    with _lock:
        if _model is not None:
            return _model
        if time.monotonic() < _retry_after:   # backing off after a recent failure
            return None
        try:
            import os

            from fastembed import TextEmbedding

            cache_dir = os.getenv("VRAKSHA_EMBED_CACHE")  # containers persist via mount
            _model = TextEmbedding(MODEL_NAME, cache_dir=cache_dir) if cache_dir else TextEmbedding(MODEL_NAME)
        except Exception as exc:  # degrade, never raise into the pipeline
            log.warning("embedding model unavailable (retry in %ss): %s", _RETRY_AFTER_S, exc)
            _retry_after = time.monotonic() + _RETRY_AFTER_S
    return _model


async def warm() -> bool:
    """Load the model now, off the event loop, so the first real turn doesn't pay
    the cold start. Best-effort: returns True if the model is ready. Called by the
    startup warmup; the lazy path still works if this is skipped."""
    return (await asyncio.to_thread(_load)) is not None


async def embed(texts: list[str]) -> list[list[float]] | None:
    """Embed texts; None means embeddings are unavailable right now."""
    if not texts:
        return []
    model = await asyncio.to_thread(_load)
    if model is None:
        return None
    try:
        vectors = await asyncio.to_thread(lambda: [list(v) for v in model.embed(texts)])
        return [[float(x) for x in vec] for vec in vectors]
    except Exception as exc:
        log.warning("embedding failed: %s", exc)
        return None
