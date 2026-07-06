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
import threading
import time
import uuid
from typing import Any

import settings
from foundation import MemoryKind, MemoryStore, constants

from .config import MEMORY_DISABLED as DISABLED
from .config import QDRANT_URL
from .embeddings import DIMS

log = logging.getLogger(__name__)

COLLECTIONS: dict[MemoryStore, str] = {
    MemoryStore.WIKI: "vraksha_wiki",
    MemoryStore.SEMANTIC: "vraksha_semantic",
    MemoryStore.EPISODIC: "vraksha_episodic",
    MemoryStore.PROCEDURAL: "vraksha_procedural",
}

_BREAKER_S = constants.CB_RECOVERY_TIMEOUT_S   # circuit-breaker recovery window (single source)
_client = None
_down_until = 0.0
_ensured: set[str] = set()
_lock = threading.Lock()


def _qdrant():
    """Lazy client + circuit breaker. Returns None while down/disabled.

    Guarded by _lock (mirrors embeddings.py's _load): every caller reaches
    this through asyncio.to_thread, so concurrent turns can race the
    check-then-act on `_client is None` from real OS threads. Without the
    lock this doesn't corrupt anything (empirically verified against the
    Kuzu analogue in graph_store.py, same shape of race) but it does
    construct and leak a redundant QdrantClient per colliding caller —
    exactly the kind of avoidable waste the batch layer's concurrent readers
    would otherwise multiply."""
    global _client, _down_until
    with _lock:
        if DISABLED or time.monotonic() < _down_until:
            return None
        if _client is None:
            try:
                from qdrant_client import QdrantClient

                _client = QdrantClient(url=QDRANT_URL, timeout=settings.MEMORY.qdrant_request_timeout_s)
            except Exception as exc:
                log.warning("qdrant client unavailable: %s", exc)
                _down_until = time.monotonic() + _BREAKER_S
                return None
        return _client


def connection():
    """Shared accessor to the lazy Qdrant client for sibling internal modules
    (`batch_store.py`) that need the SAME client + circuit-breaker state —
    mirrors `graph_store.connection()`'s precedent (a sibling reaches a named
    public wrapper, never a `_`-prefixed name directly). Unlike Kuzu, a
    second `QdrantClient` on the same server is merely wasteful, not risky
    (client-server, not embedded) — shared anyway so a batch_store fault
    trips the SAME breaker every other tier already degrades behind."""
    return _qdrant()


def trip(exc: Exception) -> None:
    """Public wrapper around `_trip` for the same reason `connection()`
    exists — `batch_store.py` shares this module's circuit breaker rather
    than keeping a second one that could disagree about whether Qdrant is
    up."""
    _trip(exc)


def is_down() -> bool:
    """True while the breaker is open (or memory is disabled) — lets the
    manager tell 'no memory found' apart from 'memory unavailable'."""
    return DISABLED or time.monotonic() < _down_until


def healthcheck() -> bool:
    """Open the Qdrant connection now (lazy client) so the first real turn doesn't
    pay the connect. Best-effort: returns True if the client is reachable, False if
    disabled/down. Called by the startup warmup."""
    return _qdrant() is not None


def _trip(exc: Exception) -> None:
    global _down_until
    log.warning("qdrant call failed (degrading for %ss): %s", _BREAKER_S, exc)
    _down_until = time.monotonic() + _BREAKER_S


def _ensure(client: Any, collection: str) -> bool:
    """Create the collection + payload indexes once (idempotent).

    user_id is the tenant key: its keyword index is marked is_tenant=True so
    Qdrant physically groups each user's points together (the documented
    multi-tenancy layout — faster tenant-scoped queries, better locality).
    Existing collections with a plain index are upgraded in place.

    Guarded by the same _lock as _qdrant(): the check-then-act on
    `collection in _ensured` has the identical race shape (empirically
    verified: 10 concurrent first-callers each issued their own
    create_collection instead of one), and a real Qdrant server may reject
    the losing calls' redundant create as an error — an avoidable, spurious
    degrade on exactly the first concurrent request after a cold start.
    """
    with _lock:
        if collection in _ensured:
            return True
        from qdrant_client import models as qm

        tenant_schema = qm.KeywordIndexParams(type=qm.KeywordIndexType.KEYWORD, is_tenant=True)
        try:
            if not client.collection_exists(collection):
                client.create_collection(
                    collection,
                    vectors_config=qm.VectorParams(size=DIMS, distance=qm.Distance.COSINE),
                )
                client.create_payload_index(collection, field_name="user_id", field_schema=tenant_schema)
                client.create_payload_index(
                    collection, field_name="session_id", field_schema=qm.PayloadSchemaType.KEYWORD
                )
            else:
                _ensure_tenant_index(client, collection, tenant_schema)
            _ensured.add(collection)
            return True
        except Exception as exc:
            _trip(exc)
            return False


def _ensure_tenant_index(client: Any, collection: str, tenant_schema: Any) -> None:
    """Upgrade a pre-existing collection's user_id index to the tenant layout."""
    info = client.get_collection(collection)
    entry = (info.payload_schema or {}).get("user_id")
    params = getattr(entry, "params", None)
    if getattr(params, "is_tenant", None):
        return
    if entry is not None:
        client.delete_payload_index(collection, field_name="user_id")
    client.create_payload_index(collection, field_name="user_id", field_schema=tenant_schema)


def _user_filter(user_id: str):
    from qdrant_client import models as qm

    # THE scope. Every read and targeted write passes through this.
    return qm.Filter(must=[qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id))])


def search(
    tier: MemoryStore, user_id: str, vector: list[float], limit: int = settings.MEMORY.search_top_k
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
        # Defense in depth: the filter above is THE scope, but a leaked hit
        # would flow straight into another user's context — so verify every
        # returned payload anyway and treat a mismatch as a security event.
        results = []
        for h in hits:
            payload = h.payload or {}
            if payload.get("user_id") != user_id:
                log.error(
                    "TENANT ISOLATION VIOLATION: %s returned a point for user %r "
                    "on a query scoped to %r — hit dropped",
                    collection, payload.get("user_id"), user_id,
                )
                continue
            results.append({"id": str(h.id), "score": float(h.score), **payload})
        return results
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
    *,
    kind: str = MemoryKind.UNSPECIFIED.value,
    valid_at: float = 0.0,
    source: str = "",
    superseded_by: str = "",
    participants: str = "",
) -> str | None:
    """Insert (or refresh, when point_id given) one memory. None on failure.

    Typed-knowledge (CB1) is additive: `kind`/`valid_at`/`source` ride the payload
    beside the existing provenance; defaults (`unspecified`/0.0/"") preserve legacy
    records read back through `.get(key, default)`. `superseded_by` is plumbed but
    inert in CB1 — EB1's manager-owned invalidation is the only writer of it.
    `participants` (CB4) is likewise additive and carried, not populated here."""
    client = _qdrant()
    collection = COLLECTIONS.get(tier)
    if client is None or collection is None or not user_id:
        return None
    if not _ensure(client, collection):
        return None
    from qdrant_client import models as qm

    memory_id = point_id or str(uuid.uuid4())
    try:
        if point_id is not None and not _owns_point(client, collection, point_id, user_id):
            # refusing is the whole point: an upsert to an existing id REPLACES
            # the point regardless of any filter — never let one user's write
            # land on another user's memory
            log.error(
                "TENANT ISOLATION VIOLATION: refused upsert to point %s in %s — "
                "it does not belong to user %r", point_id, collection, user_id,
            )
            return None
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
                        # typed-knowledge (CB1) — additive; legacy points lack these
                        # keys and read back as unspecified/0.0/"" via .get(default).
                        "kind": kind,
                        "valid_at": valid_at,
                        "source": source,
                        "superseded_by": superseded_by,
                        "participants": participants,
                    },
                )
            ],
        )
        return memory_id
    except Exception as exc:
        _trip(exc)
        return None


def _owns_point(client: Any, collection: str, point_id: str, user_id: str) -> bool:
    """True when the point doesn't exist yet (fresh insert) or belongs to user_id."""
    points = client.retrieve(collection, ids=[point_id], with_payload=["user_id"])
    if not points:
        return True
    return (points[0].payload or {}).get("user_id") == user_id


def mark_superseded(tier: MemoryStore, user_id: str, point_id: str, superseded_by: str) -> bool:
    """Patch one existing memory's `superseded_by` field in place (EB1). A targeted
    payload patch (Qdrant `set_payload`), not a full re-upsert, so the point's
    vector and every other field are untouched. Manager-only, best-effort: called
    after a confident LLM supersession judgment; a fault here must never fail the
    write that triggered it (the caller already succeeded before this runs).

    Refuses (False) when the point does not exist, or belongs to a different user.
    Unlike `_owns_point` (whose "doesn't exist yet" -> True suits a fresh insert), a
    mark on a point that isn't there must NOT silently succeed — the caller would
    believe history was annotated when nothing happened."""
    client = _qdrant()
    collection = COLLECTIONS.get(tier)
    if client is None or collection is None or not user_id or not point_id:
        return False
    try:
        points = client.retrieve(collection, ids=[point_id], with_payload=["user_id"])
        if not points or (points[0].payload or {}).get("user_id") != user_id:
            log.error(
                "refused mark_superseded on point %s in %s — missing or not owned by %r",
                point_id, collection, user_id,
            )
            return False
        client.set_payload(collection, payload={"superseded_by": superseded_by}, points=[point_id])
        return True
    except Exception as exc:
        _trip(exc)
        return False


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
            # keep going: erasure must attempt every tier, a fault in one
            # collection is no reason to leave the others populated
            _trip(exc)
