"""
CB1 typed-knowledge — behavioural proof that the additive fields are actually
POPULATED and READ BACK, not just present on the contract.

The schema-level presence of `kind`/`valid_at`/`source`/`superseded_by` is asserted
in `memory_typed_knowledge`'s sibling `memory_provenance.py`
(`test_source_document_attribution_landed`). This file proves the impl:

  ✓ the REAL `store.upsert` writes kind/valid_at/source/superseded_by into the
    Qdrant PointStruct payload — mocking only the client boundary, so a typo in
    the real payload dict fails here (closes the FakeStore-round-trip circularity)
  ✓ a typed write proposal (kind=FACT + valid_at + source) round-trips through the
    real manager write→read path and hydrates back typed
  ✓ a LEGACY hit (payload has none of the new keys) hydrates with the honest
    defaults (UNSPECIFIED / 0.0 / "") — back-compat, never raises
  ✓ a garbled stored `kind` coerces to UNSPECIFIED (fail-soft, never raises a turn)
  ✓ `superseded_by` is INERT in CB1: nothing on the write path sets it (EB1 owns
    supersession), so it always reads back ""
  ✓ stored kinds coerce fail-soft: known values survive; malformed values become
    UNSPECIFIED rather than being promoted.

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_typed_knowledge.py -v
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from foundation import (
    HydrationRequest,
    MemoryKind,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
)

from core.memory import items, store

_USER = "tk-user-alpha"
_SESSION = "tk-session-001"


# ─────────────────────────────────────────────────────────────────────────────
# Minimal in-memory store double (mirrors the real store's payload round-trip)
# ─────────────────────────────────────────────────────────────────────────────
class _MemStore:
    def __init__(self) -> None:
        self._data: dict[MemoryStore, list[dict]] = {t: [] for t in MemoryStore}

    def search(self, tier, user_id, vector, limit: int = 8) -> list[dict]:
        if limit == 1:
            return []  # dedup probe — always a miss so each write is a fresh insert
        return [
            {**item, "score": 1.0}
            for item in self._data[tier]
            if item.get("user_id") == user_id
        ][:limit]

    def upsert(
        self, tier, user_id, session_id, trace_id, vector, content,
        rationale, confidence, trust, point_id=None,
        *, kind="unspecified", valid_at=0.0, source="", superseded_by="", participants="",
    ) -> str:
        row = {
            "user_id": user_id, "session_id": session_id,
            "trace_id": trace_id, "content": content, "rationale": rationale,
            "confidence": confidence, "trust": trust, "created_at": 1000.0,
            "kind": kind, "valid_at": valid_at, "source": source,
            "superseded_by": superseded_by, "participants": participants,
        }
        if point_id is not None:  # refresh path — replace in place (like the real store)
            for p in self._data[tier]:
                if p["id"] == point_id and p["user_id"] == user_id:
                    p.update(row)
                    return point_id
        pid = point_id or f"pt-{len(self._data[tier]) + 1}"
        self._data[tier].append({"id": pid, **row})
        return pid

    def is_down(self) -> bool:
        return False


async def _fake_embed(texts: list[str]) -> list[list[float]]:
    return [[0.1] * 768 for _ in texts]


def _hydrate(manager, user_id: str, query: str = "what facts and assumptions exist?"):
    return asyncio.run(manager.hydrate(HydrationRequest(
        session_id=_SESSION,
        user_id=user_id,
        normalized=NormalizedInput(modality="text", content_type="text/plain", content=query),
    )))


def _with_double(mem: _MemStore):
    return (
        patch("core.memory.store.search", mem.search),
        patch("core.memory.store.upsert", mem.upsert),
        patch("core.memory.store.is_down", mem.is_down),
        patch("core.memory.embeddings.embed", _fake_embed),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. The REAL store.upsert writes the typed fields into the payload
#    (mock ONLY the client boundary — proves store.py, not a double)
# ─────────────────────────────────────────────────────────────────────────────
def test_real_store_upsert_writes_typed_fields_into_payload():
    captured: dict = {}

    class _FakeClient:
        def upsert(self, collection, points):
            captured["collection"] = collection
            captured["payload"] = points[0].payload

    with patch.object(store, "_qdrant", return_value=_FakeClient()), \
         patch.object(store, "_ensure", return_value=True):
        pid = store.upsert(
            MemoryStore.SEMANTIC, user_id=_USER, session_id=_SESSION, trace_id="tr",
            vector=[0.1] * 768, content="Qdrant is the vector store", rationale="why",
            confidence=0.9, trust=2,
            kind=MemoryKind.FACT.value, valid_at=123.0, source="doc://adr-0002",
        )

    assert pid is not None
    p = captured["payload"]
    # the typed-knowledge fields actually landed in the real payload dict
    assert p["kind"] == "fact", f"kind not in payload: {p.get('kind')!r}"
    assert p["valid_at"] == 123.0
    assert p["source"] == "doc://adr-0002"
    assert p["superseded_by"] == ""  # inert default, still written
    # scope + existing provenance untouched
    assert p["user_id"] == _USER
    assert p["rationale"] == "why"
    assert p["confidence"] == 0.9


# ─────────────────────────────────────────────────────────────────────────────
# 2. Typed write proposal round-trips through the real manager write→read path
# ─────────────────────────────────────────────────────────────────────────────
def test_typed_proposal_round_trips_through_hydrate():
    from core.memory.manager import MemoryManager

    mem = _MemStore()
    proposal = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content="The API standardized on Qdrant per ADR-0002.",
        rationale="architectural decision", confidence=0.9,
        kind=MemoryKind.FACT, valid_at=456.0, source="doc://adr-0002",
    )
    s, u, i, e = _with_double(mem)
    with s, u, i, e:
        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [proposal]))
        pkg = _hydrate(manager, _USER)

    assert pkg.items, "typed memory was not recalled"
    item = pkg.items[0]
    assert item.kind is MemoryKind.FACT, f"kind not surfaced: {item.kind}"
    assert item.valid_at == 456.0, f"valid_at not surfaced: {item.valid_at}"
    assert item.source == "doc://adr-0002", f"source not surfaced: {item.source!r}"
    assert item.superseded_by == ""  # inert


def test_decision_kind_and_participants_round_trip_through_hydrate():
    """CB4: a kind=DECISION proposal carrying `participants` round-trips through
    the real write/read path and is distinguishable as a category — the exact
    property EB2's 'recent decisions' query needs."""
    from core.memory.manager import MemoryManager

    mem = _MemStore()
    proposal = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content="We chose Option B: graph-first retrieval.",
        rationale="performance benchmarks favored graph traversal", confidence=0.95,
        kind=MemoryKind.DECISION, source="architecture-debate-2026-07-05",
        participants="alice (proposer), bob (reviewer)",
    )
    s, u, i, e = _with_double(mem)
    with s, u, i, e:
        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [proposal]))
        pkg = _hydrate(manager, _USER)

    assert pkg.items, "decision memory was not recalled"
    item = pkg.items[0]
    assert item.kind is MemoryKind.DECISION
    assert item.participants == "alice (proposer), bob (reviewer)"
    decisions = [i for i in pkg.items if i.kind is MemoryKind.DECISION]
    assert len(decisions) == 1, "a DECISION must be identifiable as a category, not just prose"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Back-compat: a legacy hit (no typed keys) hydrates with honest defaults
# ─────────────────────────────────────────────────────────────────────────────
def test_legacy_hit_without_typed_fields_defaults_gracefully():
    from core.memory.manager import MemoryManager

    mem = _MemStore()
    # Simulate a pre-CB1 point: NONE of the typed keys present in the payload.
    mem._data[MemoryStore.EPISODIC].append({
        "id": "legacy-1", "user_id": _USER, "session_id": _SESSION,
        "trace_id": "", "content": "A memory written before typed-knowledge landed.",
        "rationale": "legacy", "confidence": 0.9, "trust": 1, "created_at": 900.0,
    })
    s, u, i, e = _with_double(mem)
    with s, u, i, e:
        manager = MemoryManager()
        pkg = _hydrate(manager, _USER, "legacy memory")

    assert pkg.items, "legacy memory was not recalled"
    item = pkg.items[0]
    assert item.kind is MemoryKind.UNSPECIFIED, "legacy record must NOT be silently typed"
    assert item.valid_at == 0.0
    assert item.source == ""
    assert item.superseded_by == ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fail-soft: a garbled stored kind coerces to UNSPECIFIED, never raises
# ─────────────────────────────────────────────────────────────────────────────
def test_garbled_kind_coerces_to_unspecified():
    from core.memory.manager import MemoryManager

    mem = _MemStore()
    mem._data[MemoryStore.SEMANTIC].append({
        "id": "garbled-1", "user_id": _USER, "session_id": _SESSION,
        "trace_id": "", "content": "A memory with a corrupt kind value.",
        "rationale": "", "confidence": 0.9, "trust": 2, "created_at": 900.0,
        "kind": "not-a-real-kind", "valid_at": 0.0, "source": "",
    })
    s, u, i, e = _with_double(mem)
    with s, u, i, e:
        manager = MemoryManager()
        pkg = _hydrate(manager, _USER, "corrupt kind memory")

    assert pkg.items
    assert pkg.items[0].kind is MemoryKind.UNSPECIFIED


# ─────────────────────────────────────────────────────────────────────────────
# 4b. dedup refresh keeps the STRONGER typed signal (no silent FACT→ASSUMPTION)
# ─────────────────────────────────────────────────────────────────────────────
def test_dedup_refresh_does_not_downgrade_a_fact():
    from core.memory.manager import MemoryManager

    mem = _MemStore()
    # First write: a source-backed FACT.
    fact = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC, content="Qdrant is the store.",
        rationale="adr", confidence=0.9,
        kind=MemoryKind.FACT, valid_at=100.0, source="doc://adr-0002",
    )
    # A near-identical later re-write that is only an inferred ASSUMPTION with no
    # source — the dedup path must NOT let it wipe the stronger prior signal.
    barer = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC, content="Qdrant is the store.",
        rationale="restated", confidence=0.7,
        kind=MemoryKind.ASSUMPTION, valid_at=0.0, source="",
    )

    # dedup only triggers when search() reports a near-duplicate; make the probe hit.
    def _dup_search(tier, user_id, vector, limit=8):
        rows = [r for r in mem._data[tier] if r.get("user_id") == user_id]
        if limit == 1:  # dedup probe
            return [{**rows[-1], "score": 0.99}] if rows else []
        return [{**r, "score": 1.0} for r in rows][:limit]

    with patch("core.memory.store.search", _dup_search), \
         patch("core.memory.store.upsert", mem.upsert), \
         patch("core.memory.store.is_down", mem.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):
        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [fact]))
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [barer]))

    rows = mem._data[MemoryStore.SEMANTIC]
    assert len(rows) == 1, "dedup should have refreshed in place, not inserted"
    refreshed = rows[0]
    assert refreshed["kind"] == MemoryKind.FACT.value, "FACT was silently downgraded"
    assert refreshed["source"] == "doc://adr-0002", "source was wiped on refresh"
    assert refreshed["valid_at"] == 100.0, "valid_at was wiped on refresh"
    assert refreshed["confidence"] == 0.9, "confidence should stay at the max"


# ─────────────────────────────────────────────────────────────────────────────
# 5. superseded_by is inert in CB1 — the write path never sets it
# ─────────────────────────────────────────────────────────────────────────────
def test_superseded_by_is_not_expert_proposable():
    # The write-path contract carries no superseded_by — supersession is EB1's
    # manager-owned invalidation, never expert-proposed.
    import dataclasses
    proposal_fields = {f.name for f in dataclasses.fields(MemoryWriteProposal)}
    assert "superseded_by" not in proposal_fields, (
        "MemoryWriteProposal must NOT carry superseded_by — supersession is EB1"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Stored epistemic kinds fail soft without promotion.
# ─────────────────────────────────────────────────────────────────────────────
def test_stored_kind_coercion_is_honest():
    assert items._coerce_kind("fact") is MemoryKind.FACT
    assert items._coerce_kind("assumption") is MemoryKind.ASSUMPTION
    assert items._coerce_kind("decision") is MemoryKind.DECISION
    assert items._coerce_kind("FACT") is MemoryKind.UNSPECIFIED
    assert items._coerce_kind("") is MemoryKind.UNSPECIFIED
    assert items._coerce_kind("something-else") is MemoryKind.UNSPECIFIED
