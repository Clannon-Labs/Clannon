"""
C1 Persistent Cross-Session Memory — hermetic acceptance tests for the demo.

Verifies that the Day-1 seed / Day-7 hydration cycle in
``scripts/persistent_memory_demo.py`` exercises the REAL memory primitives and
produces the correct cross-session retrieval behavior — all without Qdrant or a
live embedding model.

What is hermetically certified here
────────────────────────────────────
  ✓ record_write_proposals() persists Day-1 decisions, TODOs, and assumptions
  ✓ hydrate() in a brand-new session (no transcript) retrieves those items
  ✓ All three inferred tiers (SEMANTIC, EPISODIC, PROCEDURAL) survive the cycle
  ✓ SEMANTIC items (trust=2) rank above EPISODIC/PROCEDURAL (trust=1)
  ✓ user_id scoping: a different user sees nothing (no cross-tenant leak)
  ✓ Empty user_id is fail-closed (invariant §V.20, ADR 0002)
  ✓ No degradation flag on a healthy in-memory store
  ✓ NOT-YET gaps are structurally absent from MemoryItem (not silently faked)

What is NOT certified here (honest NOT-YET)
────────────────────────────────────────────
  ✗ Typed provenance (source, author, confidence chain)  — gated on issue #16
  ✗ First-class fact-vs-assumption type labels           — gated on issue #16
  ✗ Decision-rank boost over episodic content            — gated on issue #16
  ✗ Semantic recall quality with real nomic embeddings   — live concern only

Run:
    cd backend && .venv/bin/python -m pytest tests/benchmarks/c1_persistent_memory_demo.py -v
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from foundation import HydrationRequest, MemoryItem, MemoryStore, MemoryWriteProposal


# ─────────────────────────────────────────────────────────────────────────────
# In-memory store double
#
# Captures upserts; replays stored items (score=1.0) on hydration search.
# Dedup probe (limit=1) always returns empty so each distinct proposal gets its
# own entry. The user_id filter is enforced, matching the real store's invariant.
# ─────────────────────────────────────────────────────────────────────────────


class _MemStore:
    def __init__(self, created_at_offset: float = 0.0) -> None:
        self._data: dict[MemoryStore, list[dict]] = {t: [] for t in MemoryStore}
        self.created_at_offset = created_at_offset  # seconds added to time.time() on upsert; negative = backdate

    def search(
        self, tier: MemoryStore, user_id: str, vector: list[float], limit: int = 8
    ) -> list[dict]:
        if limit == 1:
            return []  # dedup: treat every proposal as a fresh distinct entry
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
        participants: str = "",
    ) -> str | None:
        pid = point_id or str(uuid.uuid4())
        created_at = time.time() + self.created_at_offset
        for existing in self._data[tier]:
            if existing.get("id") == pid:
                existing.update(content=content, confidence=confidence, created_at=created_at)
                return pid
        self._data[tier].append(
            {
                "id": pid,
                "user_id": user_id,
                "session_id": session_id,
                "content": content,
                "score": 1.0,
                "created_at": created_at,
                "confidence": confidence,
                "trust": trust,
                # typed-knowledge (CB1) — round-trip so hydrate reads them back
                "kind": kind,
                "valid_at": valid_at,
                "source": source,
                "superseded_by": superseded_by,
                "participants": participants,
            }
        )
        return pid

    def is_down(self) -> bool:
        return False


async def _fake_embed(texts: list[str]) -> list[list[float]] | None:
    return [[0.1] * 768 for _ in texts]


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic project fixture (matches scripts/persistent_memory_demo.py)
# ─────────────────────────────────────────────────────────────────────────────

_USER = "test-c1-meridian"
_OTHER_USER = "test-c1-other-tenant"
_SESSION_DAY1 = "session-day1-a"
_SESSION_DAY7 = "session-day7-b"

_DAY1_PROPOSALS: list[MemoryWriteProposal] = [
    # SEMANTIC — architectural decisions
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "Decision [Meridian, Day 1]: Adopted vector-first memory retrieval over "
            "graph-first. Rationale: faster iteration; graph complexity deferred to Phase 2."
        ),
        rationale="architectural decision",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "Decision [Meridian, Day 1]: Single Qdrant instance with user_id payload "
            "filtering chosen over per-user collections. Operational simplicity rationale."
        ),
        rationale="architectural decision",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "Decision [Meridian, Day 1]: Subscription tiers Free / Starter $29 / Pro $79 "
            "/ Agency $199. Token budgets (not report counts) are the consumption unit."
        ),
        rationale="product decision",
        confidence=0.95,
    ),
    # EPISODIC — open TODOs and work items
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "TODO [OPEN, Day 1]: Wire Next.js frontend SSE client to real FastAPI backend. "
            "Currently mock-backed. Blocked on session-auth middleware. Priority P1."
        ),
        rationale="open work item",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "TODO [OPEN, Day 1]: Implement Stripe webhook handler for subscription tier "
            "changes. Token-budget resets must be atomic in Redis. Priority P1."
        ),
        rationale="open work item",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "TODO [OPEN, Day 1]: Harden rate limiter to key on user_id + IP, not "
            "session_id alone. Multi-tenant security gap. Must close before public beta."
        ),
        rationale="open security item",
        confidence=0.95,
    ),
    # PROCEDURAL — assumptions and constraints
    MemoryWriteProposal(
        store=MemoryStore.PROCEDURAL,
        content=(
            "Assumption [Meridian, Day 1]: Gemini free-tier (~20 RPM) is sufficient for "
            "single-user development. Production needs paid quota for multi-expert runs."
        ),
        rationale="technical assumption",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.PROCEDURAL,
        content=(
            "Assumption [Meridian, Day 1]: nomic-embed-text 768-dim vectors adequate for "
            "memory retrieval at V1 scale. To re-evaluate beyond ~10k entries per user."
        ),
        rationale="technical assumption",
        confidence=0.95,
    ),
]

_N_SEMANTIC = sum(1 for p in _DAY1_PROPOSALS if p.store is MemoryStore.SEMANTIC)
_N_EPISODIC = sum(1 for p in _DAY1_PROPOSALS if p.store is MemoryStore.EPISODIC)
_N_PROCEDURAL = sum(1 for p in _DAY1_PROPOSALS if p.store is MemoryStore.PROCEDURAL)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: seeded in-memory store + patched MemoryManager
# ─────────────────────────────────────────────────────────────────────────────


def _make_store_and_patches():
    """Return (mem_store, list_of_patch_targets) for use with unittest.mock.patch."""
    mem_store = _MemStore()
    return mem_store, [
        ("core.memory.store.search", mem_store.search),
        ("core.memory.store.upsert", mem_store.upsert),
        ("core.memory.store.is_down", mem_store.is_down),
        ("core.memory.embeddings.embed", _fake_embed),
    ]


def _hydrate(manager, user_id: str, query: str, budget: int = 8000):
    return asyncio.run(
        manager.hydrate(
            HydrationRequest(
                session_id=_SESSION_DAY7,
                user_id=user_id,
                normalized=SimpleNamespace(content=query),
                token_budget=budget,
            )
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_day7_hydration_retrieves_day1_memories():
    """Day-7 fresh session (no transcript) surfaces Day-1 seeded memories."""
    from core.memory.manager import MemoryManager

    mem_store, patches = _make_store_and_patches()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()

        # Day 1: seed via the real MemoryPort write path
        asyncio.run(manager.record_write_proposals(_USER, _SESSION_DAY1, _DAY1_PROPOSALS))

        # Confirm writes landed in the in-memory store
        semantic_stored = [i for i in mem_store._data[MemoryStore.SEMANTIC] if i["user_id"] == _USER]
        episodic_stored = [i for i in mem_store._data[MemoryStore.EPISODIC] if i["user_id"] == _USER]
        procedural_stored = [i for i in mem_store._data[MemoryStore.PROCEDURAL] if i["user_id"] == _USER]

        assert len(semantic_stored) == _N_SEMANTIC, (
            f"expected {_N_SEMANTIC} SEMANTIC writes, got {len(semantic_stored)}"
        )
        assert len(episodic_stored) == _N_EPISODIC, (
            f"expected {_N_EPISODIC} EPISODIC writes, got {len(episodic_stored)}"
        )
        assert len(procedural_stored) == _N_PROCEDURAL, (
            f"expected {_N_PROCEDURAL} PROCEDURAL writes, got {len(procedural_stored)}"
        )

        # Day 7: brand-new MemoryManager, brand-new session, no transcript
        fresh_manager = MemoryManager()
        pkg = _hydrate(fresh_manager, _USER, "What was decided and what is still open?")

        assert not pkg.degraded, "in-memory store is healthy; package must not be degraded"
        assert pkg.items, "Day-7 hydration must surface Day-1 memories with no transcript"

        # All three tiers must be represented
        tiers = {item.store for item in pkg.items}
        assert MemoryStore.SEMANTIC in tiers, "SEMANTIC decisions must be retrieved"
        assert MemoryStore.EPISODIC in tiers, "EPISODIC TODOs must be retrieved"
        assert MemoryStore.PROCEDURAL in tiers, "PROCEDURAL assumptions must be retrieved"


def test_semantic_items_rank_above_lower_trust_tiers():
    """SEMANTIC items (trust=2) must appear before EPISODIC/PROCEDURAL (trust=1)
    in the sorted package — trust is the primary ranking key."""
    from core.memory.manager import MemoryManager

    mem_store, _ = _make_store_and_patches()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION_DAY1, _DAY1_PROPOSALS))

        pkg = _hydrate(manager, _USER, "project decisions architecture")

        semantic_positions = [i for i, item in enumerate(pkg.items) if item.store is MemoryStore.SEMANTIC]
        other_positions = [i for i, item in enumerate(pkg.items) if item.store is not MemoryStore.SEMANTIC]

        assert semantic_positions, "no SEMANTIC items in package"
        assert other_positions, "need non-SEMANTIC items for comparison"
        assert max(semantic_positions) < min(other_positions), (
            "all SEMANTIC items (trust=2) must rank before EPISODIC/PROCEDURAL (trust=1); "
            f"SEMANTIC at {semantic_positions}, others at {other_positions}"
        )


def test_hydration_is_user_scoped_no_cross_tenant_leak():
    """A different user_id gets an empty package — Day-1 memories must not leak."""
    from core.memory.manager import MemoryManager

    mem_store, _ = _make_store_and_patches()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION_DAY1, _DAY1_PROPOSALS))

        other_pkg = _hydrate(manager, _OTHER_USER, "What decisions were made?")

        assert not other_pkg.items, (
            f"cross-tenant leak: {_OTHER_USER} received {len(other_pkg.items)} item(s) "
            f"belonging to {_USER}"
        )
        assert not other_pkg.degraded, (
            "empty-because-isolated must not set degraded=True"
        )


def test_empty_user_id_is_fail_closed():
    """hydrate() with an empty user_id must return an empty package without calling
    the store — the fail-closed invariant (§V.20, ADR 0002)."""
    from core.memory.manager import MemoryManager

    mem_store, _ = _make_store_and_patches()
    tripwire_calls: list[str] = []

    def _tripwire_search(*a, **k):
        tripwire_calls.append("search")
        return []

    with patch("core.memory.store.search", _tripwire_search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        pkg = asyncio.run(
            manager.hydrate(
                HydrationRequest(
                    session_id="anon",
                    user_id="",
                    normalized=SimpleNamespace(content="What was decided?"),
                    token_budget=4000,
                )
            )
        )

        assert not pkg.items, "empty user_id must yield empty items"
        assert "no user scope" in (pkg.notes or "").lower(), (
            f"expected 'no user scope' note; got: {pkg.notes!r}"
        )
        # The store must NEVER be called — fail-closed before any I/O
        assert not tripwire_calls, (
            f"store.search was called despite empty user_id: {tripwire_calls}"
        )


def test_retrieved_items_carry_basic_timestamp_provenance():
    """MemoryItem.created_at carries the unix timestamp of when the item was written.
    This is the only provenance available today. Full typed provenance is NOT-YET (#16)."""
    from core.memory.manager import MemoryManager

    mem_store, _ = _make_store_and_patches()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        before = time.time()
        asyncio.run(manager.record_write_proposals(_USER, _SESSION_DAY1, _DAY1_PROPOSALS))
        after = time.time()

        pkg = _hydrate(manager, _USER, "What was the project status?")

        for item in pkg.items:
            assert item.created_at > 0, "each MemoryItem must carry a non-zero created_at timestamp"
            assert before <= item.created_at <= after + 1, (
                f"created_at {item.created_at} is outside the expected write window "
                f"[{before}, {after}]"
            )


def test_not_yet_typed_provenance_and_fact_vs_assumption_absent_from_schema():
    """
    Structural pin: the typed-knowledge schema (CB1 / issue #16) has LANDED at the
    contract level. MemoryItem and MemoryWriteProposal now carry kind/valid_at/source;
    superseded_by is MemoryItem-only (EB1 supersession — inert in CB1, never proposable).
    Populating the fields is the core/memory impl; the CB1 verdict flips in c1_memory.py.
    author/entry_type were never part of the ratified §7.4 set and stay absent.
    """
    item_fields = {f.name for f in dataclasses.fields(MemoryItem)}
    proposal_fields = {f.name for f in dataclasses.fields(MemoryWriteProposal)}

    # Typed-knowledge fields — now PRESENT on both contracts (issue #16 shipped)
    for present_field in ("kind", "valid_at", "source"):
        assert present_field in item_fields, (
            f"typed-knowledge field '{present_field}' missing from MemoryItem"
        )
        assert present_field in proposal_fields, (
            f"typed-knowledge field '{present_field}' missing from MemoryWriteProposal"
        )
    # superseded_by is MemoryItem-only — the manager owns invalidation, experts never propose it
    assert "superseded_by" in item_fields, "superseded_by missing from MemoryItem"
    assert "superseded_by" not in proposal_fields, (
        "superseded_by must NOT be proposable (manager-owned EB1 invalidation)"
    )
    # never introduced (outside the §7.4 set)
    for absent_field in ("author", "entry_type"):
        assert absent_field not in item_fields and absent_field not in proposal_fields, (
            f"unexpected field '{absent_field}' appeared on the memory contract"
        )

    # created_at IS present (basic temporal provenance — the one we have today)
    assert "created_at" in item_fields, "MemoryItem must carry created_at for basic provenance"


def test_write_proposals_below_confidence_floor_are_not_stored():
    """The manager's write policy (confidence >= 0.6) must silently drop low-confidence
    proposals. The demo uses 0.95 so all pass; this test proves the floor exists."""
    from core.memory.manager import MemoryManager

    mem_store, _ = _make_store_and_patches()
    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()
        low_conf_proposal = MemoryWriteProposal(
            store=MemoryStore.SEMANTIC,
            content="A speculative guess that should not persist.",
            rationale="low confidence guess",
            confidence=0.3,  # below the manager's 0.6 floor
        )
        asyncio.run(
            manager.record_write_proposals(_USER, _SESSION_DAY1, [low_conf_proposal])
        )

        semantic_stored = [
            i for i in mem_store._data[MemoryStore.SEMANTIC] if i["user_id"] == _USER
        ]
        assert not semantic_stored, (
            "confidence=0.3 proposal must be rejected by the write-policy floor (0.6)"
        )


def test_recency_decay_changes_rank_within_same_tier():
    """Recency decay: an EPISODIC item written today ranks above one written 7 days
    ago within the same trust tier.

    The manager computes rank_score = raw_score * recency(created_at) where
    recency uses a 30-day half-life with a 0.5 floor:
      fresh item  → recency = 1.0   → rank_score = 1.000
      7-day item  → recency ≈ 0.925 → rank_score ≈ 0.925

    This test proves the decay function is live in the real hydration path.
    """
    from core.memory.manager import MemoryManager

    mem_store = _MemStore()

    OLD_PROPOSAL = MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content="Old note: seeded seven days ago to demonstrate recency decay ranking.",
        rationale="recency test — old item",
        confidence=0.95,
    )
    NEW_PROPOSAL = MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content="New note: seeded today to rank above the seven-day-old item.",
        rationale="recency test — new item",
        confidence=0.95,
    )

    with patch("core.memory.store.search", mem_store.search), \
         patch("core.memory.store.upsert", mem_store.upsert), \
         patch("core.memory.store.is_down", mem_store.is_down), \
         patch("core.memory.embeddings.embed", _fake_embed):

        manager = MemoryManager()

        # Write the old item backdated 7 days
        mem_store.created_at_offset = -7 * 86_400
        asyncio.run(manager.record_write_proposals(_USER, "session-old", [OLD_PROPOSAL]))

        # Write the new item at current time
        mem_store.created_at_offset = 0.0
        asyncio.run(manager.record_write_proposals(_USER, "session-new", [NEW_PROPOSAL]))

        pkg = _hydrate(manager, _USER, "what notes and open items are there?")

        episodic_items = [i for i in pkg.items if i.store is MemoryStore.EPISODIC]
        assert len(episodic_items) == 2, (
            f"expected 2 EPISODIC items for recency comparison, got {len(episodic_items)}"
        )

        # Sort by created_at to identify old vs new
        by_age = sorted(episodic_items, key=lambda i: i.created_at)
        older_item, newer_item = by_age[0], by_age[-1]

        assert newer_item.score > older_item.score, (
            f"recency decay must make the newer item rank higher: "
            f"newer={newer_item.score:.4f} (age≈0s), "
            f"older={older_item.score:.4f} (age≈7d)"
        )
        # Fresh item: recency=1.0, rank_score=1.000; 7-day item: recency≈0.925
        assert newer_item.score > 0.99, (
            f"fresh item rank_score must be close to 1.0, got {newer_item.score:.4f}"
        )
        assert older_item.score < 0.99, (
            f"7-day-old item rank_score must be < 1.0 due to decay, got {older_item.score:.4f}"
        )
