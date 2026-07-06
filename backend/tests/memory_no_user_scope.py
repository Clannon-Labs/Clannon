"""
Memory fails CLOSED on scope (invariant §V.20, ADR 0002): with no user_id there
is no tenant to scope a query to, so `hydrate` returns an empty package with an
honest "no user scope" note and a write proposal is a silent no-op — BEFORE any
Qdrant query or embedding call. `core/memory/hydration.py`'s `hydrate()` guards this at the top (the
`if not request.user_id:` return) and `core/memory/write_policy.py`'s
`record_write_proposals` (the `if not proposals or not user_id:` return).

`tests/memory_isolation.py` covers the live-Qdrant tenant-isolation layer but is
skipped when Qdrant is down, so this fail-closed branch had no coverage. This test
is hermetic: it needs no Qdrant and no embedding model, and it tripwires the
store/embedding entry points so it also proves they are never reached on the
no-scope path.

Characterizes current behavior only — it does not change the manager.
"""

import asyncio

from foundation import (
    HydrationRequest,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
)
from core.memory.manager import MemoryManager
from core.memory.hydration import _DEFAULT_BUDGET_TOKENS


def _tripwire_store_and_embeddings(monkeypatch) -> list[str]:
    """Replace every Qdrant/embedding entry point the manager can reach with a
    tripwire that records the breach and fails loudly. The fail-closed path must
    return before touching any of them, so the returned list must stay empty."""
    breaches: list[str] = []

    def _sync_trip(name):
        def _trip(*args, **kwargs):
            breaches.append(name)
            raise AssertionError(f"{name} reached on the no-user-scope path")
        return _trip

    async def _embed_trip(*args, **kwargs):
        breaches.append("embeddings.embed")
        raise AssertionError("embeddings.embed reached on the no-user-scope path")

    monkeypatch.setattr("core.memory.store.search", _sync_trip("store.search"))
    monkeypatch.setattr("core.memory.store.upsert", _sync_trip("store.upsert"))
    monkeypatch.setattr("core.memory.store.is_down", _sync_trip("store.is_down"))
    monkeypatch.setattr("core.memory.embeddings.embed", _embed_trip)
    return breaches


def test_hydrate_with_no_user_id_returns_empty_no_scope_package(monkeypatch):
    breaches = _tripwire_store_and_embeddings(monkeypatch)
    mgr = MemoryManager()

    # A fully populated request EXCEPT user_id: a real query and a wiki entry are
    # present, so if the scope gate did not fire first these would drive lexical
    # wiki selection and vector retrieval (and trip the wires).
    req = HydrationRequest(
        session_id="s",
        user_id="",
        normalized=NormalizedInput(
            modality="text", content_type="text/plain", content="who is my client"
        ),
        token_budget=1234,
        wiki=(("Client", "the user's client is Acme Corp"),),
    )

    pkg = asyncio.run(mgr.hydrate(req))

    assert pkg.items == []                                # nothing hydrated
    assert pkg.notes == "no user scope; memory skipped"   # honest, not "down"
    assert pkg.degraded is False                          # unscoped, not unavailable
    assert pkg.token_budget == 1234                       # echoes the requested budget
    assert breaches == []                                 # never touched store/embeddings


def test_hydrate_no_user_id_falls_back_to_default_budget(monkeypatch):
    _tripwire_store_and_embeddings(monkeypatch)
    mgr = MemoryManager()

    # token_budget unset (0) -> the package reports the manager's default budget.
    pkg = asyncio.run(mgr.hydrate(HydrationRequest(session_id="s", user_id="")))

    assert pkg.notes == "no user scope; memory skipped"
    assert pkg.token_budget == _DEFAULT_BUDGET_TOKENS


def test_record_write_proposals_is_a_noop_without_user_id(monkeypatch):
    breaches = _tripwire_store_and_embeddings(monkeypatch)
    mgr = MemoryManager()

    # A real, high-confidence proposal that WOULD clear the write policy and persist
    # if it were scoped — so this exercises the `not user_id` guard, not the empty
    # `not proposals` short-circuit.
    proposals = [
        MemoryWriteProposal(
            store=MemoryStore.SEMANTIC, content="a durable fact", confidence=0.99
        )
    ]

    out = asyncio.run(mgr.record_write_proposals("", "sess", proposals))

    assert out == []                # no-op: nothing persisted (empty persisted set)
    assert breaches == []           # no embedding, no store write
