"""
core/memory/hydration.py

The read side of the memory door: ranks and budgets what gets injected
before planning (ARCHITECTURE.md §4). Split out of `manager.py` (LAW 2 —
the sole-broker door was pushing 500 lines with no headroom) — same
adapter/internals relationship `graph_manager.py` has to `graph_store.py`.
`MemoryManager.hydrate()` is a thin delegation to `hydrate()` below; nothing
above `core/memory/` should ever import this file directly.

Trust-aware ranking with recency decay, a per-tier relevance floor, and
Lagrangian (water-filling) token budgeting across tiers. Every fault
degrades — memory never fails a run.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import settings
from foundation import HydrationPackage, HydrationRequest, MemoryItem, MemoryStore

from . import embeddings, items as memory_items, store
from .tiers import TIER_FLOOR, TIER_TRUST

log = logging.getLogger(__name__)

_SEARCH_K = settings.MEMORY.search_top_k              # candidates per inferred tier
_RELEVANCE_FLOOR = settings.MEMORY.relevance_floor    # drop weak hits before ranking
_RECENCY_HALF_LIFE_S = settings.MEMORY.recency_half_life_s
_RECENCY_FLOOR = settings.MEMORY.recency_floor
_MAX_CONTENT_CHARS = settings.MEMORY.max_content_chars
_DEFAULT_BUDGET_TOKENS = settings.BUDGET.default_memory_budget_tokens
_CHARS_PER_TOKEN = settings.BUDGET.memory_chars_per_token

# Real token counting for budget allocation. tiktoken's cl100k_base is not the
# embedding/generation tokenizer, but it is a far better generic estimate than the
# old len//4 heuristic — and budgeting is internal context pressure, not billing.
# Lazy + fail-soft: if the encoder can't load, fall back to the char heuristic so
# budgeting never breaks a turn (degrade-never-fail).
_ENCODER = None
_ENCODER_FAILED = False


def _count_tokens(text: str) -> int:
    global _ENCODER, _ENCODER_FAILED
    if not text:
        return 0
    if _ENCODER is None and not _ENCODER_FAILED:
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # noqa: BLE001 — never let token counting break a turn
            log.warning("tiktoken unavailable, using char heuristic: %s", exc)
            _ENCODER_FAILED = True
    if _ENCODER is not None:
        try:
            return max(1, len(_ENCODER.encode(text)))
        except Exception:  # noqa: BLE001
            pass
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _recency(created_at: float) -> float:
    age = max(0.0, time.time() - created_at)
    decay = 0.5 ** (age / _RECENCY_HALF_LIFE_S)
    return _RECENCY_FLOOR + (1.0 - _RECENCY_FLOOR) * decay


async def _embed_bounded(text: str) -> list[list[float]] | None:
    """Embed the query under a hard read deadline (settings.MEMORY.read_timeout_s).

    A cold or stalled embedding model must NOT hang the whole turn waiting on
    memory: on timeout we return None and the turn proceeds without memory (the
    worker thread keeps loading in the background, warming the model for the next
    turn). Any embedding fault degrades the same way — memory never fails a run.
    """
    try:
        return await asyncio.wait_for(
            embeddings.embed([text]), timeout=settings.MEMORY.read_timeout_s
        )
    except Exception as exc:  # noqa: BLE001 — TimeoutError or any embed fault → degrade, never raise
        log.warning("memory embed degraded (%s); answering without it", exc)
        return None


def _select_wiki(wiki: tuple, query: str, wiki_budget: int) -> list[MemoryItem]:
    """Pick the wiki entries most relevant to the query (lexical overlap),
    bounded by the wiki budget. Wiki is small and authoritative, so a couple
    of entries are included even on weak overlap — it's the source of truth."""
    if not wiki or wiki_budget <= 0:
        return []
    q_tokens = set(re.findall(r"\w+", query.lower()))
    scored: list[tuple[int, str]] = []
    for title, content in wiki:
        text = f"{title}\n{content}".strip()
        if not text:
            continue
        w_tokens = set(re.findall(r"\w+", f"{title} {content}".lower()))
        scored.append((len(q_tokens & w_tokens), text[:_MAX_CONTENT_CHARS]))
    scored.sort(key=lambda s: s[0], reverse=True)  # most relevant first; ties keep order
    items, spent = [], 0
    for _overlap, text in scored:
        cost = _count_tokens(text)
        if spent + cost > wiki_budget:
            break
        spent += cost
        items.append(MemoryItem(
            store=MemoryStore.WIKI, content=text, score=1.0,
            trust=TIER_TRUST[MemoryStore.WIKI],
        ))
    return items


async def hydrate(request: HydrationRequest) -> HydrationPackage:
    budget = request.token_budget or _DEFAULT_BUDGET_TOKENS
    if not request.user_id:
        # fail closed on scope — no user, no memory
        return HydrationPackage(token_budget=budget, notes="no user scope; memory skipped")

    query_text = (request.normalized.content if request.normalized else "") or ""
    allowed = request.allowed_tiers  # None = all tiers

    items: list[MemoryItem] = []

    # WIKI — the user-authored, highest-trust tier. Kept as TEXT (not embedded):
    # select the relevant entries by lexical overlap, bounded by the wiki floor.
    if (allowed is None or MemoryStore.WIKI in allowed) and request.wiki:
        items.extend(_select_wiki(request.wiki, query_text, int(budget * TIER_FLOOR[MemoryStore.WIKI])))

    # the inferred tiers are vector-retrieved (need the query embedded)
    inferred = [
        t for t in (MemoryStore.SEMANTIC, MemoryStore.EPISODIC, MemoryStore.PROCEDURAL)
        if allowed is None or t in allowed
    ]
    embeddable = query_text.strip()
    vectors = await _embed_bounded(query_text[:_MAX_CONTENT_CHARS]) if embeddable and inferred else None

    if embeddable and inferred and not vectors:
        # embeddings down — degrade, but still hand back any wiki we already have
        return HydrationPackage(
            items=items, token_budget=budget, degraded=not items,
            notes="memory temporarily unavailable (embeddings); answering without it" if not items else None,
        )

    per_tier: dict[MemoryStore, list[dict]] = {}
    search_faulted = False
    if vectors:
        # store.search is a sync HTTP call — run the tiers concurrently in
        # threads so hydration never blocks the event loop. Door-level guard
        # (issue #52): a tier search that RAISES (store fault mid-flight)
        # degrades to an empty tier instead of propagating out of hydrate() —
        # every fault degrades, never fails the run.
        tier_hits = await asyncio.gather(
            *(asyncio.to_thread(store.search, tier, request.user_id, vectors[0], _SEARCH_K)
              for tier in inferred),
            return_exceptions=True,
        )
        for tier, hits in zip(inferred, tier_hits):
            if isinstance(hits, BaseException):
                log.warning("memory tier search failed (%s): %s", tier.value, hits)
                search_faulted = True
                continue
            # Relevance floor: drop weak hits on RAW cosine before recency
            # weighting, so a stale-but-relevant memory is kept while a
            # fresh-but-irrelevant one is not. Without this, the store always
            # returns up to k even when every hit is weak (Phase 2 §C).
            scored = [
                {**h, "rank_score": h["score"] * _recency(float(h.get("created_at", 0)))}
                for h in hits
                if h["score"] >= _RELEVANCE_FLOOR
            ]
            scored.sort(key=lambda h: h["rank_score"], reverse=True)
            if scored:
                per_tier[tier] = scored

    if not items and not per_tier:
        if store.is_down() or search_faulted:
            # honesty: empty because the store is down (or faulted mid-gather),
            # not because the user has no memory — say so instead of pretending
            return HydrationPackage(
                token_budget=budget, degraded=True,
                notes="memory temporarily unavailable; answering without it",
            )
        return HydrationPackage(token_budget=budget, notes="no prior memory for this user")

    if per_tier:
        # Lagrangian water-filling over what's left after wiki: floors first,
        # remainder ∝ mean relevance.
        wiki_spent = sum(_count_tokens(i.content) for i in items)
        inferred_budget = max(0, budget - wiki_spent)
        floors = {t: int(inferred_budget * TIER_FLOOR[t]) for t in per_tier}
        remainder = max(0, inferred_budget - sum(floors.values()))
        means = {t: sum(h["rank_score"] for h in hs) / len(hs) for t, hs in per_tier.items()}
        total_mean = sum(means.values()) or 1.0
        allocation = {t: floors[t] + int(remainder * (means[t] / total_mean)) for t in per_tier}

        for tier, hits in per_tier.items():
            spent = 0
            for hit in hits:
                cost = _count_tokens(hit.get("content", ""))
                if spent + cost > allocation[tier]:
                    break
                spent += cost
                items.append(
                    memory_items.from_payload(
                        tier,
                        hit,
                        score=hit["rank_score"],
                    )
                )

    items.sort(key=lambda i: (i.trust, i.score), reverse=True)
    return HydrationPackage(items=items, token_budget=budget)
