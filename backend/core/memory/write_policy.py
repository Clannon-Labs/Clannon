"""
core/memory/write_policy.py

The write side of the memory door: which proposals actually persist, dedup
(hard key-upsert on near-identical content), and EB1 supersession judgment.
Split out of `manager.py` (LAW 2 — the sole-broker door was pushing 500
lines with no headroom) — same adapter/internals relationship
`graph_manager.py` has to `graph_store.py`. `MemoryManager.
record_write_proposals()`/`sync_wiki()` are thin delegations to the
functions below; nothing above `core/memory/` should ever import this file
directly.

Every failure degrades — a fault here never fails the write/turn that
triggered it (except the write itself failing honestly, per the no-
phantom-writes invariant).
"""
from __future__ import annotations

import asyncio
import logging

import settings
from foundation import MemoryKind, MemoryStore, MemoryWriteProposal

from . import embeddings, store, writer
from .tiers import TIER_TRUST

log = logging.getLogger(__name__)

_MIN_ACCEPT_CONFIDENCE = settings.MEMORY.min_accept_confidence   # semantic/procedural acceptance bar
_DEDUP_SIMILARITY = settings.MEMORY.dedup_similarity
_MAX_CONTENT_CHARS = settings.MEMORY.max_content_chars

# EB1 — supersession candidate band: close enough (by raw cosine) to plausibly be
# the same specific fact/preference restated with a changed value, but below
# _DEDUP_SIMILARITY (which is already treated as "the same point, refresh it").
# Below this floor, two memories are just topically related — not worth an LLM
# judgment (that's the relevance floor's much looser job, at retrieval time).
_SUPERSESSION_FLOOR = settings.MEMORY.supersession_floor
# Only durable-knowledge tiers are "supersedable" facts/preferences; an ordinary
# EPISODIC entry is turn history (each its own point in time, not a competing
# claim) so it's excluded here — but a DECISION is supersedable regardless of
# which tier it happens to be stored in (CB4 settled DECISION as EPISODIC; a
# decision recorded there is still exactly the kind of thing that gets revised,
# unlike a plain turn-history entry). See the `kind == DECISION` half of the
# gate at the call site — this set alone is deliberately not the full story.
_SUPERSESSION_TIERS = frozenset({MemoryStore.SEMANTIC, MemoryStore.PROCEDURAL})
# Bounds the optional judge+mark step independently of settings.MEMORY.write_timeout_s, so
# a slow judge call can never cause record_write_proposals to mistake an
# already-successful upsert for a stalled store and drop a real write.
_SUPERSESSION_TIMEOUT_S = settings.MEMORY.supersession_timeout_s


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


async def record_write_proposals(
    user_id: str, session_id: str, proposals: list[MemoryWriteProposal]
) -> list[MemoryWriteProposal]:
    """Persist the proposals that clear the write policy; return the subset that
    was ACTUALLY written.

    A proposal is DROPPED (absent from the return) when it is WORKING tier, is
    semantic/procedural below `_MIN_ACCEPT_CONFIDENCE`, has empty content, or
    the store/embeddings are down. Callers surface ONLY the returned set, so the
    `/memory` view can never show a memory that was proposed but not persisted
    (delivered-path honesty — no phantom writes). Each write is bounded by
    `settings.MEMORY.write_timeout_s`: a stalled store degrades (drops the
    rest) instead of hanging the delivered path — symmetric with the read
    path's deadline."""
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
                _persist_one(tier, user_id, session_id, content, proposal),
                timeout=settings.MEMORY.write_timeout_s,
            )
        except asyncio.TimeoutError:
            log.warning(
                "memory write timed out after %ss (store stalled) — dropping remaining writes",
                settings.MEMORY.write_timeout_s,
            )
            break  # a stalled store fails every write; bail like the embeddings-down path
        if not wrote:
            break  # embeddings down — every remaining embed would fail too
        persisted.append(proposal)
    return persisted


async def _persist_one(
    tier: MemoryStore, user_id: str, session_id: str,
    content: str, proposal: MemoryWriteProposal,
) -> str | None:
    """Embed + dedup-aware upsert one already-policy-cleared proposal. Returns
    the memory_id actually persisted, or None when nothing was — embeddings
    down, or the store itself refused/failed the upsert (a store stall instead
    surfaces as a TimeoutError to the caller's `wait_for`). The single place a
    proposal is actually written to the store; callers must treat None as "not
    persisted" (no phantom writes — this module's own invariant)."""
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
        trust=TIER_TRUST[tier],
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
        await _maybe_mark_superseded(tier, user_id, memory_id, content, existing[0], kind=kind)
    return memory_id


async def _maybe_mark_superseded(
    tier: MemoryStore, user_id: str, memory_id: str, content: str,
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


async def sync_wiki(user_id: str, title: str, content: str) -> None:
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
            confidence=1.0, trust=TIER_TRUST[MemoryStore.WIKI], point_id=point_id,
        )
