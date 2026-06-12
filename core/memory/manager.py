"""
Memory Manager — the single door to the memory layer (foundation.MemoryPort).

Real implementation per ARCHITECTURE.md: four Qdrant tiers scoped by user_id,
nomic embeddings, trust-aware ranking with recency decay, Lagrangian
(water-filling) token budgeting at hydration, and a write policy that owns
what proposals become. Every failure degrades — memory never fails a run.
"""

from __future__ import annotations

import asyncio
import logging
import time

from foundation import (
    HydrationPackage,
    HydrationRequest,
    MemoryItem,
    MemoryStore,
    MemoryWriteProposal,
)

from . import embeddings, store

log = logging.getLogger(__name__)

_TIER_TRUST = {
    MemoryStore.WIKI: 3,
    MemoryStore.SEMANTIC: 2,
    MemoryStore.EPISODIC: 1,
    MemoryStore.PROCEDURAL: 1,
}
# minimum budget floors (fractions) — ARCHITECTURE.md §4 step 5
_TIER_FLOOR = {
    MemoryStore.WIKI: 0.25,
    MemoryStore.SEMANTIC: 0.15,
    MemoryStore.EPISODIC: 0.15,
    MemoryStore.PROCEDURAL: 0.15,
}
_DEFAULT_BUDGET_TOKENS = 2000
_SEARCH_K = 8
_RECENCY_HALF_LIFE_S = 30 * 86_400
_RECENCY_FLOOR = 0.5
_MIN_ACCEPT_CONFIDENCE = 0.6   # semantic/procedural acceptance bar
_DEDUP_SIMILARITY = 0.97
_MAX_CONTENT_CHARS = 2000
_CHARS_PER_TOKEN = 4


def _recency(created_at: float) -> float:
    age = max(0.0, time.time() - created_at)
    decay = 0.5 ** (age / _RECENCY_HALF_LIFE_S)
    return _RECENCY_FLOOR + (1.0 - _RECENCY_FLOOR) * decay


class MemoryManager:
    """Qdrant-backed implementer of foundation.MemoryPort."""

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        budget = request.token_budget or _DEFAULT_BUDGET_TOKENS
        if not request.user_id:
            # fail closed on scope — no user, no memory
            return HydrationPackage(token_budget=budget, notes="no user scope; memory skipped")

        query_text = (request.normalized.content if request.normalized else "") or ""
        if not query_text.strip():
            return HydrationPackage(token_budget=budget, notes="empty query; memory skipped")

        vectors = await embeddings.embed([query_text[:_MAX_CONTENT_CHARS]])
        if not vectors:
            return HydrationPackage(token_budget=budget, notes="embeddings unavailable; memory degraded")

        tiers = list(request.allowed_tiers or _TIER_TRUST.keys())
        # store.search is a sync HTTP call — run the tiers concurrently in
        # threads so hydration never blocks the event loop (4 sequential
        # round-trips against a remote Qdrant would stall every other turn)
        tier_hits = await asyncio.gather(
            *(asyncio.to_thread(store.search, tier, request.user_id, vectors[0], _SEARCH_K)
              for tier in tiers)
        )
        per_tier: dict[MemoryStore, list[dict]] = {}
        for tier, hits in zip(tiers, tier_hits):
            scored = [
                {**h, "rank_score": h["score"] * _recency(float(h.get("created_at", 0)))}
                for h in hits
            ]
            scored.sort(key=lambda h: h["rank_score"], reverse=True)
            if scored:
                per_tier[tier] = scored

        if not per_tier:
            return HydrationPackage(token_budget=budget, notes="no prior memory for this user")

        # Lagrangian water-filling: floors first, remainder ∝ mean relevance.
        floors = {t: int(budget * _TIER_FLOOR[t]) for t in per_tier}
        remainder = max(0, budget - sum(floors.values()))
        means = {t: sum(h["rank_score"] for h in hs) / len(hs) for t, hs in per_tier.items()}
        total_mean = sum(means.values()) or 1.0
        allocation = {
            t: floors[t] + int(remainder * (means[t] / total_mean)) for t in per_tier
        }

        items: list[MemoryItem] = []
        for tier, hits in per_tier.items():
            spent = 0
            for hit in hits:
                cost = max(1, len(hit.get("content", "")) // _CHARS_PER_TOKEN)
                if spent + cost > allocation[tier]:
                    break
                spent += cost
                items.append(
                    MemoryItem(
                        store=tier,
                        content=hit.get("content", ""),
                        score=hit["rank_score"],
                        trust=_TIER_TRUST[tier],
                    )
                )

        items.sort(key=lambda i: (i.trust, i.score), reverse=True)
        return HydrationPackage(items=items, token_budget=budget)

    async def record_write_proposals(
        self, user_id: str, session_id: str, proposals: list[MemoryWriteProposal]
    ) -> None:
        if not proposals or not user_id:
            return
        for proposal in proposals:
            tier = proposal.store
            if tier == MemoryStore.WORKING:
                continue  # working memory never persists
            if tier == MemoryStore.WIKI:
                tier = MemoryStore.SEMANTIC  # wiki is user-authored only (§5)
            if tier in (MemoryStore.SEMANTIC, MemoryStore.PROCEDURAL):
                if proposal.confidence < _MIN_ACCEPT_CONFIDENCE:
                    continue
            content = proposal.content.strip()[:_MAX_CONTENT_CHARS]
            if not content:
                continue

            vectors = await embeddings.embed([content])
            if not vectors:
                return  # embeddings down — drop quietly, breaker logs it

            # dedup: refresh a near-identical memory instead of inserting
            existing = await asyncio.to_thread(store.search, tier, user_id, vectors[0], 1)
            point_id = None
            confidence = proposal.confidence
            if existing and existing[0]["score"] >= _DEDUP_SIMILARITY:
                point_id = existing[0]["id"]
                confidence = max(confidence, float(existing[0].get("confidence", 0)))

            await asyncio.to_thread(
                store.upsert,
                tier,
                user_id=user_id,
                session_id=session_id,
                trace_id="",  # trace plumbed when proposals carry it
                vector=vectors[0],
                content=content,
                rationale=proposal.rationale,
                confidence=confidence,
                trust=_TIER_TRUST[tier],
                point_id=point_id,
            )

    # ---- delivery-layer surface (not part of MemoryPort) ----------------

    async def sync_wiki(self, user_id: str, title: str, content: str) -> None:
        """Index one user-authored wiki entry (authenticated path only)."""
        text = f"{title}\n\n{content}".strip()[:_MAX_CONTENT_CHARS]
        vectors = await embeddings.embed([text])
        if vectors:
            existing = await asyncio.to_thread(store.search, MemoryStore.WIKI, user_id, vectors[0], 1)
            point_id = existing[0]["id"] if existing and existing[0]["score"] >= _DEDUP_SIMILARITY else None
            await asyncio.to_thread(
                store.upsert,
                MemoryStore.WIKI, user_id=user_id, session_id="wiki", trace_id="",
                vector=vectors[0], content=text, rationale="user-authored wiki",
                confidence=1.0, trust=_TIER_TRUST[MemoryStore.WIKI], point_id=point_id,
            )

    async def delete_user(self, user_id: str) -> None:
        """Right-to-erasure: purge every tier for this user."""
        await asyncio.to_thread(store.delete_user, user_id)


# Process-level singleton; wiring hands this to the orchestrator's ports.
manager = MemoryManager()
