"""
core/memory/store.py — Qdrant lazy-init concurrency safety.

Prime Directive audit (2026-07-05): the batch layer brings MULTIPLE concurrent
readers to the memory substrate. Two check-then-act races found in this file,
both with the identical shape and both fixed the same way (mirroring
embeddings.py's existing `_load()` lock pattern), reusing one module-level
`_lock` rather than adding a lock per race:
  1. `_qdrant()` — the lazy client init (`_client is None`) — same race shape
     found and fixed in `graph_store.py::_kuzu()` (see memory_graph_store.py's
     concurrency section).
  2. `_ensure()` — the once-per-collection provisioning (`collection in
     _ensured`) — a concurrent cold start could send a real Qdrant server
     multiple redundant create_collection calls for the same name, and a
     losing call erroring would spuriously degrade an otherwise-healthy request.

No live Qdrant required: QdrantClient/the client's methods are replaced with
counting doubles, so this proves the LOCK behavior, not real connectivity.

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_store_concurrency.py -v
"""
from __future__ import annotations

import asyncio
import threading
import time

import core.memory.store as store


def test_concurrent_cold_start_constructs_qdrant_client_exactly_once(monkeypatch):
    """Widen _qdrant()'s check-then-act window (simulating real connection
    setup latency) and prove _lock actually serializes it: N concurrent
    callers from a cold (uninitialized) state must construct QdrantClient
    exactly ONCE, not once per caller — otherwise every colliding caller
    leaks a redundant client (and its connection pool), exactly what the
    batch layer's concurrent readers would multiply on every cold start."""
    monkeypatch.setattr(store, "_client", None)
    monkeypatch.setattr(store, "_down_until", 0.0)
    construct_count = {"n": 0}
    count_lock = threading.Lock()

    class _SlowFakeClient:
        def __init__(self, url, timeout):
            with count_lock:
                construct_count["n"] += 1
            time.sleep(0.05)  # widen the race window

    import qdrant_client
    monkeypatch.setattr(qdrant_client, "QdrantClient", _SlowFakeClient)

    async def go():
        return await asyncio.gather(
            *(asyncio.to_thread(store._qdrant) for _ in range(10)),
            return_exceptions=True,
        )

    results = asyncio.run(go())
    assert not any(isinstance(r, BaseException) for r in results), (
        f"a concurrent cold start must never raise: {results}"
    )
    assert construct_count["n"] == 1, (
        f"QdrantClient() must be constructed exactly once under a concurrent "
        f"cold start, got {construct_count['n']} — the lazy-init lock isn't "
        f"serializing callers"
    )
    assert all(r is not None for r in results), "every caller must still get a usable client"


def test_concurrent_cold_start_ensures_collection_exactly_once(monkeypatch):
    """Widen _ensure()'s check-then-act window and prove the same _lock
    serializes it: N concurrent first-callers for a not-yet-provisioned
    collection must call create_collection exactly ONCE, not once per caller."""
    monkeypatch.setattr(store, "_ensured", set())
    create_count = {"n": 0}
    count_lock = threading.Lock()

    class _SlowFakeClient:
        def collection_exists(self, name):
            time.sleep(0.05)  # widen the race window
            return False

        def create_collection(self, name, vectors_config):
            with count_lock:
                create_count["n"] += 1

        def create_payload_index(self, *a, **k):
            pass

    client = _SlowFakeClient()

    async def go():
        return await asyncio.gather(
            *(asyncio.to_thread(store._ensure, client, "test_collection") for _ in range(10)),
            return_exceptions=True,
        )

    results = asyncio.run(go())
    assert not any(isinstance(r, BaseException) for r in results), (
        f"a concurrent cold start must never raise: {results}"
    )
    assert create_count["n"] == 1, (
        f"create_collection must be called exactly once under a concurrent "
        f"cold start, got {create_count['n']} — the lock isn't serializing callers"
    )
    assert all(results), "every caller must still see the collection as ensured"
