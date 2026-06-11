"""
Qdrant access — the ONLY module in the codebase that constructs memory
queries. The user_id filter is applied HERE, unconditionally, so an unscoped
read/write of user memory is structurally impossible from anywhere else
(ARCHITECTURE.md §7).

All calls degrade instead of raising: a dead Qdrant yields empty reads and
dropped writes behind a 30s circuit breaker (§6).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from foundation import MemoryStore

from .embeddings import DIMS

log = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DISABLED = os.getenv("VRAKSHA_MEMORY_DISABLED", "0") == "1"

COLLECTIONS: dict[MemoryStore, str] = {
    MemoryStore.WIKI: "vraksha_wiki",
    MemoryStore.SEMANTIC: "vraksha_semantic",
    MemoryStore.EPISODIC: "vraksha_episodic",
    MemoryStore.PROCEDURAL: "vraksha_procedural",
}

_BREAKER_S = 30.0
_client = None
_down_until = 0.0
_ensured: set[str] = set()


def _qdrant():
    """Lazy client + circuit breaker. Returns None while down/disabled."""
    global _client, _down_until
    if DISABLED or time.monotonic() < _down_until:
        return None
    if _client is None:
        try:
            from qdrant_client import QdrantClient

            _client = QdrantClient(url=QDRANT_URL, timeout=5)
        except Exception as exc:
            log.warning("qdrant client unavailable: %s", exc)
            _down_until = time.monotonic() + _BREAKER_S
            return None
    return _client


def _trip(exc: Exception) -> None:
    global _down_until
    log.warning("qdrant call failed (degrading for %ss): %s", _BREAKER_S, exc)
    _down_until = time.monotonic() + _BREAKER_S


def _ensure(client: Any, collection: str) -> bool:
    """Create the collection + payload indexes once (idempotent)."""
    if collection in _ensured:
        return True
    from qdrant_client import models as qm

    try:
        if not client.collection_exists(collection):
            client.create_collection(
                collection,
                vectors_config=qm.VectorParams(size=DIMS, distance=qm.Distance.COSINE),
            )
            for field in ("user_id", "session_id"):
                client.create_payload_index(
                    collection, field_name=field, field_schema=qm.PayloadSchemaType.KEYWORD
                )
        _ensured.add(collection)
        return True
    except Exception as exc:
        _trip(exc)
        return False


def _user_filter(user_id: str):
    from qdrant_client import models as qm

    # THE scope. Every read and targeted write passes through this.
    return qm.Filter(must=[qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id))])


def search(
    tier: MemoryStore, user_id: str, vector: list[float], limit: int = 8
) -> list[dict[str, Any]]:
    """Top-K for one tier, scoped to user_id. Returns payload dicts + score."""
    client = _qdrant()
    collection = COLLECTIONS.get(tier)
    if client is None or collection is None or not user_id:
        return []
    if not _ensure(client, collection):
        return []
    try:
        hits = client.query_points(
            collection,
            query=vector,
            limit=limit,
            query_filter=_user_filter(user_id),
            with_payload=True,
        ).points
        return [{"id": str(h.id), "score": float(h.score), **(h.payload or {})} for h in hits]
    except Exception as exc:
        _trip(exc)
        return []


def upsert(
    tier: MemoryStore,
    user_id: str,
    session_id: str,
    trace_id: str,
    vector: list[float],
    content: str,
    rationale: str,
    confidence: float,
    trust: int,
    point_id: str | None = None,
) -> str | None:
    """Insert (or refresh, when point_id given) one memory. None on failure."""
    client = _qdrant()
    collection = COLLECTIONS.get(tier)
    if client is None or collection is None or not user_id:
        return None
    if not _ensure(client, collection):
        return None
    from qdrant_client import models as qm

    memory_id = point_id or str(uuid.uuid4())
    try:
        client.upsert(
            collection,
            points=[
                qm.PointStruct(
                    id=memory_id,
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "session_id": session_id,
                        "trace_id": trace_id,
                        "tier": tier.value,
                        "content": content,
                        "rationale": rationale,
                        "confidence": confidence,
                        "trust": trust,
                        "created_at": time.time(),
                    },
                )
            ],
        )
        return memory_id
    except Exception as exc:
        _trip(exc)
        return None


def delete_user(user_id: str) -> None:
    """Erase every memory for a user across all tiers (right-to-deletion)."""
    client = _qdrant()
    if client is None or not user_id:
        return
    from qdrant_client import models as qm

    for collection in COLLECTIONS.values():
        try:
            if client.collection_exists(collection):
                client.delete(
                    collection, points_selector=qm.FilterSelector(filter=_user_filter(user_id))
                )
        except Exception as exc:
            _trip(exc)
            return
