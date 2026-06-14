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

log = logging.getLogger(__name__)

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
DIMS = 768

_model = None
_failed = False
_lock = threading.Lock()


def _load():
    global _model, _failed
    with _lock:
        if _model is not None or _failed:
            return _model
        try:
            import os

            from fastembed import TextEmbedding

            cache_dir = os.getenv("VRAKSHA_EMBED_CACHE")  # containers persist via mount
            _model = TextEmbedding(MODEL_NAME, cache_dir=cache_dir) if cache_dir else TextEmbedding(MODEL_NAME)
        except Exception as exc:  # degrade, never raise into the pipeline
            log.warning("embedding model unavailable: %s", exc)
            _failed = True
    return _model


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
