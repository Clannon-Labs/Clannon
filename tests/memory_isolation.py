"""Tenant isolation guarantees of the memory store (live Qdrant, skipped when down).

The filter scope itself is covered by tests/orchestrator_ports.py; these tests
cover the defense-in-depth layer: hostile/buggy callers must not be able to
write across tenants, and the tenant index layout must actually be applied.
"""

import os
import urllib.request
import uuid

import pytest

from foundation import MemoryStore
from core.memory import store


def _qdrant_up() -> bool:
    try:
        urllib.request.urlopen(
            os.getenv("QDRANT_URL", "http://localhost:6333") + "/readyz", timeout=2
        )
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _qdrant_up(), reason="qdrant not reachable")

_VEC = [0.1] * 768


def test_upsert_refuses_foreign_point_id():
    owner, attacker = (f"test-{uuid.uuid4().hex[:8]}" for _ in range(2))
    try:
        point = store.upsert(
            MemoryStore.EPISODIC, user_id=owner, session_id="s", trace_id="",
            vector=_VEC, content="owner secret", rationale="", confidence=1.0, trust=1,
        )
        assert point is not None

        # an upsert to an existing id replaces the point wholesale — the store
        # must refuse when the id belongs to someone else
        hijack = store.upsert(
            MemoryStore.EPISODIC, user_id=attacker, session_id="s", trace_id="",
            vector=_VEC, content="overwritten", rationale="", confidence=1.0, trust=1,
            point_id=point,
        )
        assert hijack is None

        hits = store.search(MemoryStore.EPISODIC, owner, _VEC, limit=3)
        assert any(h["content"] == "owner secret" for h in hits)   # intact
        assert all(h["content"] != "overwritten" for h in hits)
    finally:
        store.delete_user(owner)
        store.delete_user(attacker)


def test_same_user_dedup_refresh_still_works():
    user = f"test-{uuid.uuid4().hex[:8]}"
    try:
        point = store.upsert(
            MemoryStore.EPISODIC, user_id=user, session_id="s", trace_id="",
            vector=_VEC, content="v1", rationale="", confidence=0.5, trust=1,
        )
        refreshed = store.upsert(
            MemoryStore.EPISODIC, user_id=user, session_id="s", trace_id="",
            vector=_VEC, content="v2", rationale="", confidence=0.9, trust=1,
            point_id=point,
        )
        assert refreshed == point   # the legitimate dedup path is unaffected
    finally:
        store.delete_user(user)


def test_user_id_index_is_tenant_marked():
    user = f"test-{uuid.uuid4().hex[:8]}"
    try:
        store.upsert(   # triggers _ensure (create or upgrade)
            MemoryStore.EPISODIC, user_id=user, session_id="s", trace_id="",
            vector=_VEC, content="x", rationale="", confidence=1.0, trust=1,
        )
        client = store._qdrant()
        info = client.get_collection(store.COLLECTIONS[MemoryStore.EPISODIC])
        params = info.payload_schema["user_id"].params
        assert getattr(params, "is_tenant", False) is True
    finally:
        store.delete_user(user)
