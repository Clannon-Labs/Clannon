"""
core/memory/batch_store.py

Qdrant mechanics for the cross-batch awareness slice (`BatchAwarenessPort`) —
a sibling to `store.py`, not a fifth tier inside it. Batch-lifecycle status
is a complete, deterministic filter (current state), never a ranked cosine
search, so it does not belong on `store.py`'s `COLLECTIONS`/`search`/`upsert`
path (that machinery is built for relevance-ranked retrieval, which is
meaningless here — ratified 2026-07-05,
`proposals/archive/to-backend/2026-07-05_cross-batch-awareness-memory-design.md`
§3).

Shares `store.py`'s Qdrant client + circuit breaker via `store.connection()`/
`store.trip()` (a second `QdrantClient` on the same server would be merely
wasteful, not risky — client-server, unlike Kuzu's embedded model — but
sharing the breaker means a batch_store fault degrades the SAME way every
other tier already does, not a second breaker that could disagree).

`BatchAwarenessManager` (`batch_awareness_manager.py`) is the sole caller;
nothing above `core/memory/` should ever import this file directly.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from foundation import BatchLifecycleStatus

from . import store

log = logging.getLogger(__name__)

_COLLECTION = "vraksha_batch_status"

# Q3 knobs (ratified) — the aggregate this pair produces is the actual size
# bound: 50 * 200 = 10,000 chars ~= 2,500 tokens at full saturation.
MAX_BATCHES_PER_MISSION = 50    # → config/backend/ (public: batch_awareness_manager.py's read-side truncation reads this)
_HEADLINE_CHAR_CAP = 200        # → config/backend/

# An outer safety ceiling on the raw scroll read, distinct from the
# per-response truncation cap above — bounds the read itself so an
# adversarial/corrupt mission with far more points than any realistic batch
# count still can't turn this into an unbounded scan.
_RAW_SCROLL_LIMIT = 10_000

# Deterministic (not random-literal) namespace for the uuid5 point-id
# derivation — a fixed function of a fixed string, so it never needs to be
# "remembered" as an opaque constant.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "clannon.batch_status")

# Vestigial vector — this collection is never queried by similarity, only
# scrolled by payload filter. A constant 1-dim vector satisfies Qdrant's
# schema requirement at minimum storage cost.
_VECTOR = [0.0]

_ensured = False
_ensure_lock = threading.Lock()


@dataclass(slots=True)
class BatchStatusReadResult:
    """Internal read shape — `BatchAwarenessManager` adapts this to the
    port's `CrossBatchAwareness`. `rows` are raw Qdrant payload dicts (one
    per batch); `total` is the true count before any truncation the manager
    applies. `degraded=True` means the store was wanted but unavailable —
    distinct from a healthy empty result (scope valid, store up, genuinely
    no other batches yet)."""
    rows: tuple[dict[str, Any], ...] = ()
    total: int = 0
    degraded: bool = False
    notes: str = ""


def _point_id(user_id: str, mission_id: str, batch_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{user_id}:{mission_id}:{batch_id}"))


def _ensure(client: Any) -> bool:
    """Create the collection + its (user_id, mission_id) payload indexes
    once (idempotent) — mirrors `store._ensure`'s shape, INCLUDING its
    lock-guarded check-then-act discipline: `store.connection()` acquires
    and releases `store`'s lock before returning, so this function runs
    unlocked unless it holds its own — the identical race `store._ensure`/
    `graph_store._kuzu` already guard against (empirically verified there:
    concurrent cold-start callers each independently pass `collection_exists
    -> False` and each call `create_collection`; the losers raise, tripping
    the shared breaker and degrading every tier for the recovery window)."""
    global _ensured
    if _ensured:
        return True
    with _ensure_lock:
        if _ensured:
            return True
        from qdrant_client import models as qm

        tenant_schema = qm.KeywordIndexParams(type=qm.KeywordIndexType.KEYWORD, is_tenant=True)
        try:
            if not client.collection_exists(_COLLECTION):
                client.create_collection(
                    _COLLECTION,
                    vectors_config=qm.VectorParams(size=len(_VECTOR), distance=qm.Distance.COSINE),
                )
                client.create_payload_index(_COLLECTION, field_name="user_id", field_schema=tenant_schema)
                client.create_payload_index(
                    _COLLECTION, field_name="mission_id", field_schema=qm.PayloadSchemaType.KEYWORD
                )
            _ensured = True
            return True
        except Exception as exc:
            store.trip(exc)
            return False


def _owns_point(client: Any, point_id: str, user_id: str) -> bool:
    """True when the point doesn't exist yet (fresh insert) or belongs to
    user_id — identical discipline to `store._owns_point`."""
    points = client.retrieve(_COLLECTION, ids=[point_id], with_payload=["user_id"])
    if not points:
        return True
    return (points[0].payload or {}).get("user_id") == user_id


def record_batch_status(
    user_id: str, mission_id: str, batch_id: str, domain: str,
    status: BatchLifecycleStatus, headline: str,
) -> bool:
    """Deterministic key-upsert of ONE current-status record for
    (user_id, mission_id, batch_id) — a HARD replace (MERGE-by-id-equivalent
    for Qdrant: `client.upsert` to the same derived id always replaces the
    whole payload), never the cosine-dedup soft-merge `store.upsert` uses.
    Returns whether it was actually persisted — no phantom-write claims.
    Fail-closed on any missing id; refuses (logs + returns False) if the
    derived point already belongs to a different user_id (defense in depth
    against a hash collision or a caller passing a foreign combination)."""
    if not user_id or not mission_id or not batch_id:
        return False
    client = store.connection()
    if client is None or not _ensure(client):
        return False
    from qdrant_client import models as qm

    point_id = _point_id(user_id, mission_id, batch_id)
    try:
        if not _owns_point(client, point_id, user_id):
            log.error(
                "TENANT ISOLATION VIOLATION: refused batch-status upsert to point %s — "
                "it does not belong to user %r", point_id, user_id,
            )
            return False
        client.upsert(
            _COLLECTION,
            points=[
                qm.PointStruct(
                    id=point_id,
                    vector=_VECTOR,
                    payload={
                        "user_id": user_id,
                        "mission_id": mission_id,
                        "batch_id": batch_id,
                        "domain": domain,
                        "status": status.value,
                        "headline": headline[:_HEADLINE_CHAR_CAP],
                        "updated_at": time.time(),
                    },
                )
            ],
        )
        return True
    except Exception as exc:
        store.trip(exc)
        return False


def scroll_batch_statuses(user_id: str, mission_id: str) -> BatchStatusReadResult:
    """Every batch-status point for (user_id, mission_id) — a complete
    filter-read via Qdrant `scroll` (payload-filter only, no query vector),
    never a ranked search. Sort/truncate/status-priority logic lives in the
    manager, not here (this module is pure Qdrant mechanics). Fail-closed on
    a missing user_id/mission_id; degrades on a store fault."""
    if not user_id or not mission_id:
        return BatchStatusReadResult(degraded=True, notes="missing user_id or mission_id — refused, fail-closed")
    client = store.connection()
    if client is None or not _ensure(client):
        return BatchStatusReadResult(degraded=True, notes="batch store unavailable")
    from qdrant_client import models as qm

    scroll_filter = qm.Filter(must=[
        qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id)),
        qm.FieldCondition(key="mission_id", match=qm.MatchValue(value=mission_id)),
    ])
    try:
        points, _ = client.scroll(
            _COLLECTION, scroll_filter=scroll_filter, limit=_RAW_SCROLL_LIMIT, with_payload=True,
        )
        rows = tuple(p.payload for p in points if p.payload and p.payload.get("user_id") == user_id)
        return BatchStatusReadResult(rows=rows, total=len(rows))
    except Exception as exc:
        store.trip(exc)
        return BatchStatusReadResult(degraded=True, notes="batch store unavailable")


def clear_mission(user_id: str, mission_id: str) -> None:
    """Delete every batch-status point for (user_id, mission_id) — the fix
    for unbounded lifetime growth across a user's missions (the per-mission
    read bound doesn't bound the collection's total size; this is the sweep
    that does). No-op on a missing id or a down store; never raises."""
    if not user_id or not mission_id:
        return
    client = store.connection()
    if client is None:
        return
    from qdrant_client import models as qm

    scroll_filter = qm.Filter(must=[
        qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id)),
        qm.FieldCondition(key="mission_id", match=qm.MatchValue(value=mission_id)),
    ])
    try:
        if client.collection_exists(_COLLECTION):
            client.delete(_COLLECTION, points_selector=qm.FilterSelector(filter=scroll_filter))
    except Exception as exc:
        store.trip(exc)


def delete_user(user_id: str) -> None:
    """Erase every batch-status point for a user (right-to-erasure) —
    mirrors `store.delete_user` exactly. Required per the ratification: a
    collection outside `store.COLLECTIONS` is otherwise silently exempt from
    erasure."""
    if not user_id:
        return
    client = store.connection()
    if client is None:
        return
    from qdrant_client import models as qm

    try:
        if client.collection_exists(_COLLECTION):
            client.delete(
                _COLLECTION,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(must=[qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id))])
                ),
            )
    except Exception as exc:
        store.trip(exc)
