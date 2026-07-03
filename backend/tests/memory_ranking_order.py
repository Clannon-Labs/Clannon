"""
Hermetic harness pinning the memory ranking-order contract that MemoryManager.hydrate()
enforces but no test yet covers.

  (a) TRUST ORDERING -- on equal relevance, a higher-trust WIKI record (trust=3) must
      rank before a lower-trust EPISODIC record (trust=1). Non-Negotiable Priority:
      user-authored knowledge outranks inferred memory.
      Contract: manager.py:195 sort(key=lambda i: (i.trust, i.score), reverse=True)
      driven by _TIER_TRUST at manager.py:58-63: WIKI=3 > SEMANTIC=2 > EPISODIC/PROCEDURAL=1.

  (b) RECENCY DECAY -- at equal relevance and equal trust, a newer record must rank before
      an older one. Contract: rank_score = raw_score * _recency(created_at) at manager.py:153,
      where _recency() (manager.py:82-85) applies exponential half-life decay so a fresh
      memory beats a stale one at the same cosine distance.

Hermetic: test-double store and embedder; no network; no paid keys.
Every request is user_id-scoped per the MANDATORY fail-closed invariant (ADR 0002 / §V.20).
Each test prints a ranked-order table and a trust-ordered / recency-ordered / VIOLATED verdict.
On a genuine ordering divergence: writes a needs-reviewer note and fails loudly WITHOUT
editing manager.py or any ranking/trust/recency/scoping logic.

Distinct from:
  tests/memory_tools.py    -- schema-level trust field formatting only (hardcodes trust=5/2)
  tests/memory_isolation.py -- cross-tenant write isolation on the real Qdrant store
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from foundation import HydrationRequest, MemoryItem, MemoryStore, NormalizedInput
from core.memory.manager import (
    MemoryManager,
    _RECENCY_HALF_LIFE_S,
    _RELEVANCE_FLOOR,
    _TIER_TRUST,
    _recency,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

_USER = "test-ranking-u1"
_SESSION = "test-ranking-s1"
_DUMMY_VECS = [[0.1] * 768]   # shape embeddings.embed returns: list[list[float]]

_NEEDS_REVIEWER = "/home/amrit/.clannon_proposal"


def _make_request(
    query: str = "ranking contract test query",
    wiki: tuple = (),
    token_budget: int = 4000,
) -> HydrationRequest:
    return HydrationRequest(
        session_id=_SESSION,
        user_id=_USER,
        normalized=NormalizedInput(
            modality="text",
            content_type="text/plain",
            content=query,
        ),
        token_budget=token_budget,
        wiki=wiki,
    )


def _make_store_hit(content: str, score: float, created_at: float) -> dict:
    """Synthesize a raw store-search result dict matching what store.search returns."""
    return {
        "id": f"synthetic-{abs(hash(content)) % 100_000}",
        "content": content,
        "score": score,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _print_ranked_table(items: list[MemoryItem], title: str) -> None:
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    print(f"  {'rank':<5} {'store':<12} {'trust':<7} {'score':<12} content[:50]")
    print(f"  {'-'*67}")
    for rank, item in enumerate(items, 1):
        print(
            f"  {rank:<5} {item.store.value:<12} {item.trust:<7} "
            f"{item.score:<12.6f} {item.content[:50]!r}"
        )
    print(f"{'='*72}")


def _open_needs_reviewer(violation: str) -> None:
    """Append a needs-reviewer escalation for a ranking-contract violation."""
    note = (
        "\n--- MEMORY RANKING CONTRACT VIOLATION (tests/memory_ranking_order.py) ---\n"
        f"{violation}\n"
        "Do NOT edit manager.py to hide this. The harness pins the CONTRACT, not a workaround.\n"
        "Options:\n"
        "  1. Confirm the contract changed intentionally and update this harness.\n"
        "  2. Fix the ranking logic in core/memory/manager.py hydrate().\n"
        "---\n"
    )
    try:
        with open(_NEEDS_REVIEWER, "a") as fh:
            fh.write(note)
        print(f"[needs-reviewer] violation note appended to {_NEEDS_REVIEWER}")
    except OSError as exc:
        print(f"[needs-reviewer] could not write note: {exc}")


# ---------------------------------------------------------------------------
# (0) Contract constants -- fast, no I/O
# ---------------------------------------------------------------------------


def test_tier_trust_constants_match_documented_values():
    """Pin _TIER_TRUST to the documented ordering. If these change, ALL ordering
    guarantees must be re-evaluated."""
    assert _TIER_TRUST[MemoryStore.WIKI] == 3, "WIKI trust changed from documented 3"
    assert _TIER_TRUST[MemoryStore.SEMANTIC] == 2, "SEMANTIC trust changed from documented 2"
    assert _TIER_TRUST[MemoryStore.EPISODIC] == 1, "EPISODIC trust changed from documented 1"
    assert _TIER_TRUST[MemoryStore.PROCEDURAL] == 1, "PROCEDURAL trust changed from documented 1"
    assert _TIER_TRUST[MemoryStore.WIKI] > _TIER_TRUST[MemoryStore.SEMANTIC]
    assert _TIER_TRUST[MemoryStore.SEMANTIC] > _TIER_TRUST[MemoryStore.EPISODIC]
    assert _TIER_TRUST[MemoryStore.EPISODIC] == _TIER_TRUST[MemoryStore.PROCEDURAL]
    print(
        "\n_TIER_TRUST: WIKI=3 > SEMANTIC=2 > EPISODIC=PROCEDURAL=1"
        " -- contract constants CONFIRMED"
    )


def test_recency_function_newer_yields_higher_weight():
    """Pin that _recency() assigns a strictly higher weight to a newer timestamp."""
    now = time.time()
    old = now - 60 * 86_400  # 60 days ago (two half-lives)
    assert _recency(now) > _recency(old), (
        f"_recency(now)={_recency(now):.4f} is not > _recency(old)={_recency(old):.4f}; "
        f"half-life={_RECENCY_HALF_LIFE_S}s"
    )
    print(
        f"\n_recency: now={_recency(now):.4f} > 60-days-ago={_recency(old):.4f}"
        " -- recency function CONFIRMED"
    )


# ---------------------------------------------------------------------------
# (a) TRUST ORDERING via hydrate() with test doubles
# ---------------------------------------------------------------------------


def test_trust_ordering_wiki_beats_episodic_at_equal_score():
    """
    WIKI (trust=3) must rank before EPISODIC (trust=1) when both carry equal
    relevance. Drives the real MemoryManager.hydrate() with test-double store
    and embedder; asserts the final sort at manager.py:195.

    Setup:
      - WIKI entry supplied via request.wiki (lexical path, no embedding needed).
        _select_wiki assigns score=1.0 and trust=3.
      - EPISODIC hit returned by the fake store.search with raw_score=1.0 and
        created_at=now so recency ~ 1.0, yielding rank_score ~ 1.0 (equal to WIKI).
    """
    now = time.time()
    wiki_entries = (("ranking contract", "wiki entry about ranking contract testing"),)
    episodic_hit = _make_store_hit(
        content="episodic: this is inferred memory about ranking",
        score=1.0,
        created_at=now,
    )

    async def _fake_embed(texts):
        return _DUMMY_VECS

    def _fake_search(tier, user_id, vector, limit):
        assert user_id == _USER, f"user_id scope violated: got {user_id!r}"
        if tier == MemoryStore.EPISODIC:
            return [episodic_hit]
        return []

    manager = MemoryManager()
    with (
        patch("core.memory.embeddings.embed", side_effect=_fake_embed),
        patch("core.memory.store.search", side_effect=_fake_search),
        patch("core.memory.store.is_down", return_value=False),
    ):
        pkg = asyncio.run(
            manager.hydrate(_make_request(
                query="ranking contract test query",
                wiki=wiki_entries,
            ))
        )

    items = pkg.items
    _print_ranked_table(items, "TRUST ORDERING: WIKI (trust=3) vs EPISODIC (trust=1)")

    wiki_items = [i for i in items if i.store == MemoryStore.WIKI]
    epis_items = [i for i in items if i.store == MemoryStore.EPISODIC]

    assert wiki_items, "no WIKI items in result -- check wiki_entries or _select_wiki path"
    assert epis_items, "no EPISODIC items in result -- check _fake_search or relevance floor"

    wiki_rank = items.index(wiki_items[0])
    epis_rank = items.index(epis_items[0])

    print(
        f"\n  WIKI: rank={wiki_rank + 1}, trust={wiki_items[0].trust}, score={wiki_items[0].score:.6f}"
    )
    print(
        f"  EPISODIC: rank={epis_rank + 1}, trust={epis_items[0].trust}, score={epis_items[0].score:.6f}"
    )

    if wiki_rank >= epis_rank:
        violation = (
            f"TRUST ORDERING VIOLATED: WIKI (trust={wiki_items[0].trust}, score={wiki_items[0].score:.4f}) "
            f"ranked at position {wiki_rank + 1} but EPISODIC "
            f"(trust={epis_items[0].trust}, score={epis_items[0].score:.4f}) "
            f"ranked at position {epis_rank + 1}. "
            f"Expected WIKI rank < EPISODIC rank (lower index = higher priority). "
            f"Check manager.py:195 sort and _TIER_TRUST constants at manager.py:58-63."
        )
        _open_needs_reviewer(violation)
        pytest.fail(violation)

    print("\n  Verdict: trust-ordered (PASS)")


def test_trust_ordering_wiki_beats_semantic_at_equal_score():
    """WIKI (trust=3) must also rank before SEMANTIC (trust=2)."""
    now = time.time()
    wiki_entries = (("ranking contract", "wiki entry about ranking contract testing"),)
    semantic_hit = _make_store_hit(
        content="semantic: inferred knowledge about ranking",
        score=1.0,
        created_at=now,
    )

    async def _fake_embed(texts):
        return _DUMMY_VECS

    def _fake_search(tier, user_id, vector, limit):
        assert user_id == _USER, f"user_id scope violated: got {user_id!r}"
        if tier == MemoryStore.SEMANTIC:
            return [semantic_hit]
        return []

    manager = MemoryManager()
    with (
        patch("core.memory.embeddings.embed", side_effect=_fake_embed),
        patch("core.memory.store.search", side_effect=_fake_search),
        patch("core.memory.store.is_down", return_value=False),
    ):
        pkg = asyncio.run(
            manager.hydrate(_make_request(
                query="ranking contract test query",
                wiki=wiki_entries,
            ))
        )

    items = pkg.items
    _print_ranked_table(items, "TRUST ORDERING: WIKI (trust=3) vs SEMANTIC (trust=2)")

    wiki_items = [i for i in items if i.store == MemoryStore.WIKI]
    sem_items = [i for i in items if i.store == MemoryStore.SEMANTIC]

    assert wiki_items, "no WIKI items in result"
    assert sem_items, "no SEMANTIC items in result"

    wiki_rank = items.index(wiki_items[0])
    sem_rank = items.index(sem_items[0])

    print(
        f"\n  WIKI: rank={wiki_rank + 1}, trust={wiki_items[0].trust}, score={wiki_items[0].score:.6f}"
    )
    print(
        f"  SEMANTIC: rank={sem_rank + 1}, trust={sem_items[0].trust}, score={sem_items[0].score:.6f}"
    )

    if wiki_rank >= sem_rank:
        violation = (
            f"TRUST ORDERING VIOLATED: WIKI (trust={wiki_items[0].trust}) "
            f"ranked at position {wiki_rank + 1} but SEMANTIC "
            f"(trust={sem_items[0].trust}) ranked at position {sem_rank + 1}."
        )
        _open_needs_reviewer(violation)
        pytest.fail(violation)

    print("\n  Verdict: trust-ordered (PASS)")


# ---------------------------------------------------------------------------
# (b) RECENCY DECAY via hydrate() with test doubles
# ---------------------------------------------------------------------------


def test_recency_newer_episodic_beats_older_at_equal_raw_score():
    """
    At equal raw relevance AND equal trust, the newer EPISODIC record must rank
    first. Drives hydrate() with two EPISODIC hits at the same raw cosine score but
    different created_at; verifies the recency-weighted rank_score reorders them.

    The fake store returns the OLD hit first so any pass-through ordering is ruled out.
    """
    now = time.time()
    old_created_at = now - 60 * 86_400   # 60 days ago: decay = 0.5^2 = 0.25
    new_created_at = now                  # just now:    decay = 0.5^0 = 1.0

    raw_score = 0.50   # comfortably above _RELEVANCE_FLOOR (0.30); equal for both hits

    old_hit = _make_store_hit(
        content="old episodic: stale memory from sixty days ago",
        score=raw_score,
        created_at=old_created_at,
    )
    new_hit = _make_store_hit(
        content="new episodic: fresh insight written just now",
        score=raw_score,
        created_at=new_created_at,
    )

    async def _fake_embed(texts):
        return _DUMMY_VECS

    def _fake_search(tier, user_id, vector, limit):
        assert user_id == _USER, f"user_id scope violated: got {user_id!r}"
        if tier == MemoryStore.EPISODIC:
            # Deliberately return old first to rule out pass-through ordering.
            return [old_hit, new_hit]
        return []

    manager = MemoryManager()
    with (
        patch("core.memory.embeddings.embed", side_effect=_fake_embed),
        patch("core.memory.store.search", side_effect=_fake_search),
        patch("core.memory.store.is_down", return_value=False),
    ):
        pkg = asyncio.run(manager.hydrate(_make_request(query="fresh insight needed")))

    items = pkg.items
    _print_ranked_table(items, "RECENCY DECAY: newer vs older at equal raw score")

    new_recency = _recency(new_created_at)
    old_recency = _recency(old_created_at)
    print(
        f"\n  Raw score (both): {raw_score}"
        f"\n  Recency weights:  new={new_recency:.4f}  old={old_recency:.4f}"
        f"\n  Rank scores:      new={raw_score * new_recency:.6f}"
        f"  old={raw_score * old_recency:.6f}"
    )

    assert new_recency > old_recency, (
        f"_recency() returned wrong ordering: new={new_recency:.4f} old={old_recency:.4f}"
    )

    epis_items = [i for i in items if i.store == MemoryStore.EPISODIC]
    assert len(epis_items) >= 2, (
        f"expected >=2 EPISODIC items in result, got {len(epis_items)}; "
        f"check _RELEVANCE_FLOOR ({_RELEVANCE_FLOOR}) vs raw_score ({raw_score})"
    )

    new_pos = next(
        (pos for pos, item in enumerate(items) if item.content == new_hit["content"]),
        None,
    )
    old_pos = next(
        (pos for pos, item in enumerate(items) if item.content == old_hit["content"]),
        None,
    )

    assert new_pos is not None, "newer hit not found in hydrated items"
    assert old_pos is not None, "older hit not found in hydrated items"

    print(
        f"\n  New item: rank={new_pos + 1}, score={items[new_pos].score:.6f}"
    )
    print(
        f"  Old item: rank={old_pos + 1}, score={items[old_pos].score:.6f}"
    )

    if new_pos >= old_pos:
        violation = (
            f"RECENCY DECAY VIOLATED: newer EPISODIC item "
            f"(recency={new_recency:.4f}, rank_score={raw_score * new_recency:.4f}) "
            f"ranked at position {new_pos + 1} but older item "
            f"(recency={old_recency:.4f}, rank_score={raw_score * old_recency:.4f}) "
            f"ranked at position {old_pos + 1}. "
            f"Expected newer at lower index (higher rank). "
            f"Check manager.py:153 recency weighting and manager.py:195 sort."
        )
        _open_needs_reviewer(violation)
        pytest.fail(violation)

    print("\n  Verdict: recency-ordered (PASS)")


def test_recency_within_semantic_tier():
    """Same recency contract verified on the SEMANTIC tier (trust=2)."""
    now = time.time()
    old_created_at = now - 45 * 86_400   # 45 days ago: 1.5 half-lives
    new_created_at = now

    raw_score = 0.60

    old_hit = _make_store_hit(
        content="semantic old: fact stored six weeks ago",
        score=raw_score,
        created_at=old_created_at,
    )
    new_hit = _make_store_hit(
        content="semantic new: fact stored today",
        score=raw_score,
        created_at=new_created_at,
    )

    async def _fake_embed(texts):
        return _DUMMY_VECS

    def _fake_search(tier, user_id, vector, limit):
        assert user_id == _USER, f"user_id scope violated: got {user_id!r}"
        if tier == MemoryStore.SEMANTIC:
            return [old_hit, new_hit]
        return []

    manager = MemoryManager()
    with (
        patch("core.memory.embeddings.embed", side_effect=_fake_embed),
        patch("core.memory.store.search", side_effect=_fake_search),
        patch("core.memory.store.is_down", return_value=False),
    ):
        pkg = asyncio.run(manager.hydrate(_make_request(query="recent fact needed")))

    items = pkg.items
    _print_ranked_table(items, "RECENCY DECAY (SEMANTIC tier): newer vs older")

    new_recency = _recency(new_created_at)
    old_recency = _recency(old_created_at)

    sem_items = [i for i in items if i.store == MemoryStore.SEMANTIC]
    assert len(sem_items) >= 2, (
        f"expected >=2 SEMANTIC items, got {len(sem_items)}"
    )

    new_pos = next(
        (pos for pos, item in enumerate(items) if item.content == new_hit["content"]),
        None,
    )
    old_pos = next(
        (pos for pos, item in enumerate(items) if item.content == old_hit["content"]),
        None,
    )

    assert new_pos is not None and old_pos is not None

    print(
        f"\n  Recency: new={new_recency:.4f}  old={old_recency:.4f}"
        f"\n  Rank:    new={new_pos + 1}  old={old_pos + 1}"
    )

    if new_pos >= old_pos:
        violation = (
            f"RECENCY DECAY VIOLATED (SEMANTIC): newer item ranked at {new_pos + 1} "
            f"but older item ranked at {old_pos + 1}."
        )
        _open_needs_reviewer(violation)
        pytest.fail(violation)

    print("\n  Verdict: recency-ordered (PASS)")


# ---------------------------------------------------------------------------
# (c) USER_ID SCOPE: ranking must never cross tenant boundaries
# ---------------------------------------------------------------------------


def test_no_cross_user_results_in_ranking():
    """The ranking harness itself must only hydrate items for _USER.
    Verifies the test-double enforces user_id scope on every store.search call."""
    call_user_ids: list[str] = []

    async def _fake_embed(texts):
        return _DUMMY_VECS

    def _fake_search(tier, user_id, vector, limit):
        call_user_ids.append(user_id)
        if tier == MemoryStore.EPISODIC:
            return [_make_store_hit("scoped memory", 0.8, time.time())]
        return []

    manager = MemoryManager()
    with (
        patch("core.memory.embeddings.embed", side_effect=_fake_embed),
        patch("core.memory.store.search", side_effect=_fake_search),
        patch("core.memory.store.is_down", return_value=False),
    ):
        asyncio.run(manager.hydrate(_make_request()))

    assert call_user_ids, "store.search was never called -- hydration skipped early"
    assert all(uid == _USER for uid in call_user_ids), (
        f"user_id scope violated: search called with {set(call_user_ids)!r}, expected only {_USER!r}"
    )
    print(f"\n  All {len(call_user_ids)} store.search calls used user_id={_USER!r} -- scope CONFIRMED")
