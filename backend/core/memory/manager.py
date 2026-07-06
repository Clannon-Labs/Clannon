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
import re
import time

from foundation import (
    HydrationPackage,
    HydrationRequest,
    MemoryItem,
    MemoryKind,
    MemoryStore,
    MemoryWriteProposal,
    constants,
)

from . import embeddings, graph_manager, store, writer

log = logging.getLogger(__name__)

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
_SEARCH_K = constants.MEMORY_SEARCH_TOP_K          # candidates per inferred tier
_RELEVANCE_FLOOR = constants.MEMORY_RELEVANCE_FLOOR  # drop weak hits before ranking
_RECENCY_HALF_LIFE_S = 30 * 86_400
_RECENCY_FLOOR = 0.5
_MIN_ACCEPT_CONFIDENCE = 0.6   # semantic/procedural acceptance bar
_DEDUP_SIMILARITY = 0.97
_MAX_CONTENT_CHARS = 2000
_CHARS_PER_TOKEN = 4

# EB1 — supersession candidate band: close enough (by raw cosine) to plausibly be
# the same specific fact/preference restated with a changed value, but below
# _DEDUP_SIMILARITY (which is already treated as "the same point, refresh it").
# Below this floor, two memories are just topically related — not worth an LLM
# judgment (that's _RELEVANCE_FLOOR's much looser job, at retrieval time).
_SUPERSESSION_FLOOR = 0.85
# Only durable-knowledge tiers are "supersedable" facts/preferences; an ordinary
# EPISODIC entry is turn history (each its own point in time, not a competing
# claim) so it's excluded here — but a DECISION is supersedable regardless of
# which tier it happens to be stored in (CB4 settled DECISION as EPISODIC; a
# decision recorded there is still exactly the kind of thing that gets revised,
# unlike a plain turn-history entry). See the `kind == DECISION` half of the
# gate at the call site — this set alone is deliberately not the full story.
_SUPERSESSION_TIERS = frozenset({MemoryStore.SEMANTIC, MemoryStore.PROCEDURAL})
# Bounds the optional judge+mark step independently of MEMORY_WRITE_TIMEOUT_S, so
# a slow judge call can never cause record_write_proposals to mistake an
# already-successful upsert for a stalled store and drop a real write.
_SUPERSESSION_TIMEOUT_S = 5.0


# Epistemic strength ordering — a dedup refresh keeps the STRONGER kind, so a
# barer re-write of a source-backed fact never silently downgrades it to an
# inferred assumption (symmetric with confidence=max on refresh). DECISION is a
# CATEGORY not an epistemic status (a decision is itself asserted), so it ranks
# with FACT — but DECISION never actually reaches this comparison in practice,
# since decision-involved pairs skip the merge branch entirely (see
# _persist_one). Ranked anyway, and every lookup is .get(kind, 0)-safe, so nothing
# KeyErrors if that invariant is ever loosened.
_KIND_RANK = {
    MemoryKind.UNSPECIFIED: 0,
    MemoryKind.ASSUMPTION: 1,
    MemoryKind.FACT: 2,
    MemoryKind.DECISION: 2,
}


def _coerce_kind(raw: object) -> MemoryKind:
    """Map a stored `kind` payload value back to MemoryKind, fail-soft. A legacy
    point has no `kind` (raw is None) and an unknown/garbled value must never raise
    into a turn — both degrade to UNSPECIFIED (the honest 'untyped' default)."""
    try:
        return MemoryKind(raw)
    except (ValueError, KeyError):
        return MemoryKind.UNSPECIFIED


def _recency(created_at: float) -> float:
    age = max(0.0, time.time() - created_at)
    decay = 0.5 ** (age / _RECENCY_HALF_LIFE_S)
    return _RECENCY_FLOOR + (1.0 - _RECENCY_FLOOR) * decay


async def _embed_bounded(text: str) -> list[list[float]] | None:
    """Embed the query under a hard read deadline (MEMORY_READ_TIMEOUT_S).

    A cold or stalled embedding model must NOT hang the whole turn waiting on
    memory: on timeout we return None and the turn proceeds without memory (the
    worker thread keeps loading in the background, warming the model for the next
    turn). Any embedding fault degrades the same way — memory never fails a run.
    """
    try:
        return await asyncio.wait_for(
            embeddings.embed([text]), timeout=constants.MEMORY_READ_TIMEOUT_S
        )
    except Exception as exc:  # noqa: BLE001 — TimeoutError or any embed fault → degrade, never raise
        log.warning("memory embed degraded (%s); answering without it", exc)
        return None


class MemoryManager:
    """Qdrant-backed implementer of foundation.MemoryPort."""

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
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
            items.extend(self._select_wiki(request.wiki, query_text, int(budget * _TIER_FLOOR[MemoryStore.WIKI])))

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
            floors = {t: int(inferred_budget * _TIER_FLOOR[t]) for t in per_tier}
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
                    items.append(MemoryItem(
                        store=tier, content=hit.get("content", ""),
                        score=hit["rank_score"], trust=_TIER_TRUST[tier],
                        created_at=float(hit.get("created_at", 0.0)),
                        rationale=hit.get("rationale", ""),
                        confidence=float(hit.get("confidence", 0.0)),
                        session_id=hit.get("session_id", ""),
                        trace_id=hit.get("trace_id", ""),
                        # typed-knowledge (CB1) — legacy hits lack these keys and
                        # fall back to the contract defaults via .get().
                        kind=_coerce_kind(hit.get("kind")),
                        valid_at=float(hit.get("valid_at", 0.0)),
                        source=hit.get("source", ""),
                        superseded_by=hit.get("superseded_by", ""),
                        participants=hit.get("participants", ""),
                    ))

        items.sort(key=lambda i: (i.trust, i.score), reverse=True)
        return HydrationPackage(items=items, token_budget=budget)

    def _select_wiki(self, wiki: tuple, query: str, wiki_budget: int) -> list[MemoryItem]:
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
                trust=_TIER_TRUST[MemoryStore.WIKI],
            ))
        return items

    async def record_write_proposals(
        self, user_id: str, session_id: str, proposals: list[MemoryWriteProposal]
    ) -> list[MemoryWriteProposal]:
        """Persist the proposals that clear the write policy; return the subset that
        was ACTUALLY written.

        A proposal is DROPPED (absent from the return) when it is WORKING tier, is
        semantic/procedural below `_MIN_ACCEPT_CONFIDENCE`, has empty content, or
        the store/embeddings are down. Callers surface ONLY the returned set, so the
        `/memory` view can never show a memory that was proposed but not persisted
        (delivered-path honesty — no phantom writes). Each write is bounded by
        `MEMORY_WRITE_TIMEOUT_S`: a stalled store degrades (drops the rest) instead
        of hanging the delivered path — symmetric with the read path's deadline."""
        persisted: list[MemoryWriteProposal] = []
        if not proposals or not user_id:
            return persisted
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
            try:
                wrote = await asyncio.wait_for(
                    self._persist_one(tier, user_id, session_id, content, proposal),
                    timeout=constants.MEMORY_WRITE_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                log.warning(
                    "memory write timed out after %ss (store stalled) — dropping remaining writes",
                    constants.MEMORY_WRITE_TIMEOUT_S,
                )
                break  # a stalled store fails every write; bail like the embeddings-down path
            if not wrote:
                break  # embeddings down — every remaining embed would fail too
            persisted.append(proposal)
        return persisted

    async def _persist_one(
        self, tier: MemoryStore, user_id: str, session_id: str,
        content: str, proposal: MemoryWriteProposal,
    ) -> str | None:
        """Embed + dedup-aware upsert one already-policy-cleared proposal. Returns
        the memory_id actually persisted, or None when nothing was — embeddings
        down, or the store itself refused/failed the upsert (a store stall instead
        surfaces as a TimeoutError to the caller's `wait_for`). The single place a
        proposal is actually written to the store; callers must treat None as "not
        persisted" (no phantom writes — the manager's own invariant)."""
        vectors = await embeddings.embed([content])
        if not vectors:
            return None  # embeddings down — drop quietly, breaker logs it
        # dedup: refresh a near-identical memory instead of inserting
        existing = await asyncio.to_thread(store.search, tier, user_id, vectors[0], 1)
        point_id = None
        confidence = proposal.confidence
        kind, valid_at, source = proposal.kind, proposal.valid_at, proposal.source
        participants = proposal.participants
        existing_kind = _coerce_kind(existing[0].get("kind")) if existing else MemoryKind.UNSPECIFIED
        # CB4: a DECISION record is append-only in EITHER direction — a DECISION
        # proposal never merges into an existing point, AND an existing DECISION is
        # never merged into by anything else (an ordinary fact that happens to
        # resemble a decision's wording must not silently overwrite it either). No
        # matter how closely they resemble each other, this always inserts fresh and
        # offers itself to the EB1 supersession judge below instead (both records
        # retained, linked) — never the silent content/rationale overwrite
        # dedup-merge would otherwise do (CB4's "reasoning is lost" fail condition).
        decision_involved = proposal.kind == MemoryKind.DECISION or existing_kind == MemoryKind.DECISION
        if existing and existing[0]["score"] >= _DEDUP_SIMILARITY and not decision_involved:
            point_id = existing[0]["id"]
            prev = existing[0]
            confidence = max(confidence, float(prev.get("confidence", 0)))
            # keep the stronger typed signal on refresh (never downgrade a
            # source-backed fact into a barer re-write's assumption)
            prev_kind = existing_kind
            if _KIND_RANK.get(prev_kind, 0) > _KIND_RANK.get(kind, 0):
                kind = prev_kind
            source = source or prev.get("source", "")
            valid_at = valid_at or float(prev.get("valid_at", 0.0))
            participants = participants or prev.get("participants", "")
        memory_id = await asyncio.to_thread(
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
            # typed-knowledge (CB1) — carry the proposer's epistemic type +
            # temporal validity + source through to the payload (dedup-merged
            # above to keep the stronger signal). superseded_by is NOT threaded
            # here: supersession is manager-owned EB1 work, never expert-proposed
            # (MemoryWriteProposal has no such field).
            kind=kind.value,
            valid_at=valid_at,
            source=source,
            participants=participants,
        )
        # EB1: `existing` was searched BEFORE this upsert, so it can never be this
        # same memory — self-supersession is structurally impossible here, not
        # merely excluded by the similarity band. Only a fresh insert (point_id
        # was None going in — a dedup-merge is a refresh of the SAME fact, not a
        # competing one) is a candidate. CB4: a DECISION is always a candidate
        # regardless of its tier (settled as EPISODIC) — see _SUPERSESSION_TIERS'
        # own comment on why the tier check alone isn't the full story.
        supersession_eligible = tier in _SUPERSESSION_TIERS or kind == MemoryKind.DECISION
        if memory_id and point_id is None and supersession_eligible and existing:
            await self._maybe_mark_superseded(tier, user_id, memory_id, content, existing[0], kind=kind)
        return memory_id

    async def _maybe_mark_superseded(
        self, tier: MemoryStore, user_id: str, memory_id: str, content: str,
        candidate: dict, *, kind: MemoryKind,
    ) -> None:
        """EB1, best-effort: judge whether the memory just written supersedes the
        closest existing hit found before the write. Any fault here — judge or
        mark, including this step's own timeout — must never surface: the
        underlying write already landed and this is pure annotation on top of it."""
        score = candidate.get("score", 0.0)
        if score < _SUPERSESSION_FLOOR:
            return
        # CB4: a DECISION never took the merge branch (see _persist_one), so ANY
        # resemblance — including >= _DEDUP_SIMILARITY, the exact band a merge
        # would otherwise silently overwrite in — is a supersession candidate.
        # Every other kind keeps the existing upper bound: that band means "the
        # same fact, already merged," not a competing claim to judge.
        if kind != MemoryKind.DECISION and score >= _DEDUP_SIMILARITY:
            return
        try:
            supersedes = await asyncio.wait_for(
                writer.judge_supersession(content, candidate.get("content", "")),
                timeout=_SUPERSESSION_TIMEOUT_S,
            )
            if not supersedes:
                return
            ok = await asyncio.to_thread(
                store.mark_superseded, tier, user_id, candidate["id"], memory_id
            )
            if not ok:
                log.warning("supersession mark failed for %s -> %s", candidate["id"], memory_id)
        except Exception as exc:  # noqa: BLE001 — best-effort annotation, never affects the write that landed
            log.warning("supersession judgment/mark failed: %s", exc)

    async def learn(
        self, user_id: str, session_id: str, *, task: str, answer: str, findings: list[str]
    ) -> None:
        """The background memory-agent: distil semantic facts + procedural patterns
        from a finished turn and persist what clears the write policy. Best-effort —
        a fault here never affects the turn that already answered the user."""
        if not user_id:
            return
        try:
            proposals = await writer.distill(task, answer, findings)
        except Exception as exc:  # noqa: BLE001 — never let learning break a turn
            log.warning("memory distillation failed: %s", exc)
            return
        if proposals:
            await self.record_write_proposals(user_id, session_id, proposals)

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
        """Right-to-erasure: purge every tier for this user — the four
        Qdrant vector tiers plus the graph tier (CodeFile + Mission/Task),
        which used to be silently skipped here."""
        await asyncio.to_thread(store.delete_user, user_id)
        await graph_manager.manager.delete_user(user_id)


# Process-level singleton; wiring hands this to the orchestrator's ports.
manager = MemoryManager()
