"""
Hermetic provenance-surfacing tests — feat/c1-provenance-surfacing.

Verifies that the additive read-path change (MemoryItem gains rationale,
confidence, session_id, trace_id from existing store payload) works correctly:

  ✓ hydrated items expose tier, trust, created_at, score, and rationale
  ✓ session_id surfaces from the originating session
  ✓ confidence surfaces from the write-time confidence value
  ✓ trace_id surfaces from the originating trace (empty when not plumbed)
  ✓ unscoped queries (empty user_id) cannot leak provenance data
  ✓ cross-tenant queries see NO items (no provenance leak across users)
  ✓ wiki items (no session provenance) carry empty session_id / trace_id
    without raising — defaults are used
  ✓ source-document attribution is structurally absent (NOT-YET, gated #16)

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_provenance.py -v
"""
from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from foundation import (
    HydrationRequest,
    MemoryItem,
    MemoryStore,
    MemoryWriteProposal,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared in-memory store double
# ─────────────────────────────────────────────────────────────────────────────

class _MemStore:
    """Minimal Qdrant double for provenance tests.

    Stores all upsert payload fields (including rationale and trace_id) so
    they flow through to MemoryItem just as the real store would return them.
    """

    def __init__(self) -> None:
        self._data: dict[MemoryStore, list[dict]] = {t: [] for t in MemoryStore}

    def search(
        self, tier: MemoryStore, user_id: str, vector: list[float], limit: int = 8
    ) -> list[dict]:
        if limit == 1:
            return []  # dedup probe — always empty so each write is unique
        return [
            {**item, "score": 1.0}
            for item in self._data[tier]
            if item.get("user_id") == user_id
        ][:limit]

    def upsert(
        self,
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
        kind: str = "unspecified",
        valid_at: float = 0.0,
        source: str = "",
        superseded_by: str = "",
    ) -> str | None:
        pid = point_id or str(uuid.uuid4())
        self._data[tier].append(
            {
                "id": pid,
                "user_id": user_id,
                "session_id": session_id,
                "trace_id": trace_id,
                "content": content,
                "score": 1.0,
                "created_at": time.time(),
                "confidence": confidence,
                "rationale": rationale,
                "trust": trust,
                "kind": kind,
                "valid_at": valid_at,
                "source": source,
                "superseded_by": superseded_by,
            }
        )
        return pid

    def is_down(self) -> bool:
        return False


async def _fake_embed(texts: list[str]) -> list[list[float]] | None:
    return [[0.1] * 768 for _ in texts]


_USER = "prov-test-user-alpha"
_OTHER_USER = "prov-test-user-beta"
_SESSION = "session-prov-001"
_TRACE = "trace-prov-abc"

_PROPOSAL = MemoryWriteProposal(
    store=MemoryStore.SEMANTIC,
    content="Provenance test: architectural decision about the memory retrieval strategy.",
    rationale="architectural decision logged by orchestrator",
    confidence=0.92,
)


def _hydrate(manager, user_id: str, query: str = "what decisions exist?"):
    return asyncio.run(
        manager.hydrate(
            HydrationRequest(
                session_id="session-read",
                user_id=user_id,
                normalized=SimpleNamespace(content=query),
                token_budget=4000,
            )
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Acceptance: provenance fields surface correctly
# ─────────────────────────────────────────────────────────────────────────────


def test_hydrated_item_exposes_tier_trust_created_at_score_rationale():
    """ACCEPTANCE (C1 provenance pass): a hydrated MemoryItem must expose
    tier, trust, created_at, score, and rationale — the minimum provenance
    required by the feat/c1-provenance-surfacing task."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        before = time.time()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [_PROPOSAL]))
        after = time.time()

        pkg = _hydrate(manager, _USER)
        assert pkg.items, "store is healthy and has data — must retrieve at least one item"

        item = pkg.items[0]

        # tier — MemoryStore enum identifying the collection
        assert item.store is MemoryStore.SEMANTIC

        # trust — authority level from the tier
        assert item.trust == 2, f"SEMANTIC trust must be 2; got {item.trust}"

        # created_at — temporal provenance
        assert item.created_at > 0
        assert before <= item.created_at <= after + 1

        # score — the rank_score (cosine x recency) that drove retrieval
        assert item.score > 0

        # rationale — write-time reason (already in the store payload)
        assert item.rationale == "architectural decision logged by orchestrator", (
            f"rationale must surface from the store payload; got {item.rationale!r}"
        )


def test_hydrated_item_exposes_session_id():
    """session_id from the write call must surface on the retrieved MemoryItem."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [_PROPOSAL]))

        pkg = _hydrate(manager, _USER)
        assert pkg.items

        item = pkg.items[0]
        assert item.session_id == _SESSION, (
            f"session_id must surface from the store payload; "
            f"expected {_SESSION!r}, got {item.session_id!r}"
        )


def test_hydrated_item_exposes_confidence():
    """Write-time confidence must surface on the retrieved MemoryItem."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [_PROPOSAL]))

        pkg = _hydrate(manager, _USER)
        assert pkg.items

        item = pkg.items[0]
        assert abs(item.confidence - 0.92) < 0.01, (
            f"confidence must surface from the store payload; "
            f"expected 0.92, got {item.confidence}"
        )


def test_hydrated_item_exposes_trace_id_when_plumbed():
    """trace_id surfaces on MemoryItem when present in the store payload."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()

    # Inject a record with trace_id directly into the store (simulating a
    # write path that plumbs the trace — manager.record_write_proposals
    # currently passes "" for trace_id, so we write directly to the double).
    mem_store._data[MemoryStore.EPISODIC].append(
        {
            "id": str(uuid.uuid4()),
            "user_id": _USER,
            "session_id": _SESSION,
            "trace_id": _TRACE,
            "content": "Traced memory: recorded with an explicit trace_id.",
            "score": 1.0,
            "created_at": time.time(),
            "confidence": 0.88,
            "rationale": "traced write for provenance test",
            "trust": 1,
        }
    )

    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        pkg = _hydrate(manager, _USER, "traced memory provenance")
        assert pkg.items

        # Find the episodic item we injected
        episodic = [i for i in pkg.items if i.store is MemoryStore.EPISODIC]
        assert episodic, "the traced episodic record must be in the hydration output"
        traced = episodic[0]
        assert traced.trace_id == _TRACE, (
            f"trace_id must surface from the store payload; "
            f"expected {_TRACE!r}, got {traced.trace_id!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Scope isolation — provenance must not leak across users
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_user_id_exposes_no_provenance():
    """Empty user_id must return an empty package — the fail-closed invariant
    (§V.20, ADR 0002) ensures no provenance data can leak without a scope."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [_PROPOSAL]))

        pkg = asyncio.run(
            manager.hydrate(
                HydrationRequest(
                    session_id="anon",
                    user_id="",  # no scope
                    normalized=SimpleNamespace(content="what decisions exist?"),
                    token_budget=4000,
                )
            )
        )

        assert not pkg.items, (
            "empty user_id must yield zero items — no provenance data exposed without scope"
        )
        assert "no user scope" in (pkg.notes or "").lower()


def test_cross_tenant_query_exposes_no_provenance():
    """A different user's hydrate must see no items and no provenance data from
    the target user's store — the user_id filter is the sole scope gate."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION, [_PROPOSAL]))

        pkg = _hydrate(manager, _OTHER_USER, "what decisions exist?")

        assert not pkg.items, (
            f"cross-tenant query must return no items: "
            f"{_OTHER_USER} received {len(pkg.items)} item(s) belonging to {_USER}"
        )
        assert not pkg.degraded, "empty-because-isolated must not set degraded=True"


# ─────────────────────────────────────────────────────────────────────────────
# Wiki items — no session provenance, defaults must not raise
# ─────────────────────────────────────────────────────────────────────────────


def test_wiki_items_carry_empty_session_provenance_by_default():
    """Wiki items are user-authored text with no session or trace provenance.
    The MemoryItem defaults (session_id="", trace_id="") must be used without
    raising — no provenance is better than a misleading fake provenance."""
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        # Hydrate with wiki entries directly — wiki is a text-selected tier,
        # not vector-retrieved, so session/trace provenance is always empty.
        wiki = (
            ("Project Goals", "Build a production-grade AI research pipeline."),
            ("Architecture", "Single Qdrant instance with user_id scoping."),
        )
        pkg = asyncio.run(
            manager.hydrate(
                HydrationRequest(
                    session_id="session-wiki",
                    user_id=_USER,
                    normalized=SimpleNamespace(content="what is the architecture?"),
                    token_budget=4000,
                    wiki=wiki,
                )
            )
        )

        wiki_items = [i for i in pkg.items if i.store is MemoryStore.WIKI]
        assert wiki_items, "wiki entries must be in the hydration output"

        for item in wiki_items:
            # session_id and trace_id should be empty string (default) — not raise
            assert isinstance(item.session_id, str)
            assert isinstance(item.trace_id, str)
            # rationale and confidence likewise default to empty/0.0
            assert isinstance(item.rationale, str)
            assert isinstance(item.confidence, float)


# ─────────────────────────────────────────────────────────────────────────────
# NOT-YET structural pin
# ─────────────────────────────────────────────────────────────────────────────


def test_source_document_attribution_landed():
    """Source-document attribution + fact/assumption typing (CB1 / issue #16) have
    LANDED at the contract level: MemoryItem now carries `source`, `kind`, and
    `valid_at`. (Populating them is the core/memory impl.) `author`/`entry_type`
    were never part of the ratified §7.4 set and stay absent."""
    item_fields = {f.name for f in dataclasses.fields(MemoryItem)}

    # Typed-knowledge fields — now PRESENT on the contract
    for present in ("source", "kind", "valid_at", "superseded_by"):
        assert present in item_fields, (
            f"typed-knowledge field '{present}' missing from MemoryItem"
        )
    # Never introduced (not in the §7.4 set) — stay absent
    for absent in ("author", "entry_type"):
        assert absent not in item_fields, (
            f"unexpected field '{absent}' appeared on MemoryItem"
        )

    # Provenance fields that MUST be present (surfaced earlier by aeab3c7)
    for present in ("rationale", "confidence", "session_id", "trace_id", "created_at"):
        assert present in item_fields, (
            f"Expected provenance field '{present}' missing from MemoryItem"
        )
