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
import time

import settings
from foundation import (
    EdgeLabel,
    EdgeOrigin,
    GraphEdge,
    GraphNode,
    GraphScope,
    MemoryItem,
    MemoryKind,
    MemorySaver,
    MemoryStore,
    MemoryTurn,
    MemoryWriteProposal,
    NodeLabel,
)

from . import embeddings, graph_manager, graph_store, store, writer
from .items import _coerce_kind
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

# CB2/CB3 graph twin — which epistemic kinds get mirrored onto the knowledge
# web. Gate is on `kind`, NOT tier (a DECISION is EPISODIC but must still get
# a graph twin — see the ratified correction in HANDOFF_batch.md); UNSPECIFIED
# stays excluded, same as it's excluded from supersession eligibility.
_GRAPH_TWIN_KINDS = frozenset({MemoryKind.FACT, MemoryKind.ASSUMPTION, MemoryKind.DECISION})
# Same bounded, best-effort, annotation-only shape as _SUPERSESSION_TIMEOUT_S —
# the memory itself already persisted; this whole step is pure best-effort
# enrichment on top of an already-successful write.
_GRAPH_TWIN_TIMEOUT_S = settings.MEMORY.supersession_timeout_s
# §3.2 — bounds the CONTRADICTS candidate fan-out regardless of how many
# existing CLAIMs share an entity with the newly-written one; same funnel
# discipline as the rest of the write policy (never an all-pairs compare).
_MAX_CONTRADICTION_CANDIDATES = 5


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


async def record_write_proposals(
    user_id: str,
    session_id: str,
    proposals: list[MemoryWriteProposal],
    *,
    saved_by: MemorySaver = MemorySaver.UNSPECIFIED,
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
    persisted = await _persist_proposals(
        user_id,
        session_id,
        proposals,
        trace_id="",
        saved_by=saved_by,
    )
    return [proposal for proposal, _tier, _memory_id in persisted]


async def persist_curated(
    turn: MemoryTurn,
    proposals: list[MemoryWriteProposal],
) -> list[MemoryItem]:
    """Persist successful curator tool actions with code-owned provenance."""
    persisted = await _persist_proposals(
        turn.user_id,
        turn.session_id,
        proposals,
        trace_id=turn.trace_id,
        saved_by=MemorySaver.MEMORY_CURATOR,
    )
    by_id: dict[str, MemoryItem] = {}
    for proposal, tier, memory_id in persisted:
        by_id[memory_id] = MemoryItem(
            store=tier,
            content=proposal.content.strip()[:_MAX_CONTENT_CHARS],
            memory_id=memory_id,
            trust=TIER_TRUST[tier],
            created_at=time.time(),
            rationale=proposal.rationale,
            confidence=proposal.confidence,
            session_id=turn.session_id,
            trace_id=turn.trace_id,
            saved_by=MemorySaver.MEMORY_CURATOR,
            kind=proposal.kind,
            valid_at=proposal.valid_at,
            source=proposal.source,
            participants=proposal.participants,
        )
    return list(by_id.values())


async def _persist_proposals(
    user_id: str,
    session_id: str,
    proposals: list[MemoryWriteProposal],
    *,
    trace_id: str,
    saved_by: MemorySaver,
) -> list[tuple[MemoryWriteProposal, MemoryStore, str]]:
    """Shared bounded persistence loop for curator and legacy tooling."""
    persisted: list[tuple[MemoryWriteProposal, MemoryStore, str]] = []
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
            memory_id = await asyncio.wait_for(
                _persist_one(
                    tier,
                    user_id,
                    session_id,
                    content,
                    proposal,
                    trace_id=trace_id,
                    saved_by=saved_by,
                ),
                timeout=settings.MEMORY.write_timeout_s,
            )
        except asyncio.TimeoutError:
            log.warning(
                "memory write timed out after %ss (store stalled) — dropping remaining writes",
                settings.MEMORY.write_timeout_s,
            )
            break  # a stalled store fails every write; bail like the embeddings-down path
        if not memory_id:
            break  # embeddings down — every remaining embed would fail too
        persisted.append((proposal, tier, memory_id))
    return persisted


async def _persist_one(
    tier: MemoryStore, user_id: str, session_id: str,
    content: str, proposal: MemoryWriteProposal,
    *,
    trace_id: str = "",
    saved_by: MemorySaver = MemorySaver.SYSTEM,
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
    is_new = point_id is None  # captured before store.upsert below decides the real id
    upsert_kwargs = {
        "user_id": user_id,
        "session_id": session_id,
        "trace_id": trace_id,
        "vector": vectors[0],
        "content": content,
        "rationale": proposal.rationale,
        "confidence": confidence,
        "trust": TIER_TRUST[tier],
        "point_id": point_id,
        # typed-knowledge (CB1) — carry the proposer's epistemic type +
        # temporal validity + source through to the payload (dedup-merged
        # above to keep the stronger signal). superseded_by is NOT threaded
        # here: supersession is manager-owned EB1 work, never expert-proposed
        # (MemoryWriteProposal has no such field).
        "kind": kind.value,
        "valid_at": valid_at,
        "source": source,
        "participants": participants,
    }
    if saved_by is not MemorySaver.UNSPECIFIED:
        upsert_kwargs["saved_by"] = saved_by.value
    memory_id = await asyncio.to_thread(store.upsert, tier, **upsert_kwargs)
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
    # CB2/CB3: only on a genuinely fresh point — a dedup-merge refresh reuses
    # the same memory_id (Fact/Claim's `content` is create_only anyway, so a
    # repeat extraction of the same text would be pure waste, not a change).
    if memory_id and is_new and kind in _GRAPH_TWIN_KINDS:
        await _write_graph_twin(user_id, memory_id, content, kind, participants)
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


def _normalize_entity_name(name: str) -> str:
    """Canonical form for Entity convergence (§1.1 of the ratified knowledge-
    web design): collapsed whitespace, lowercased — "Memory  Manager" and
    "memory manager" must land on the same node, not fork into two."""
    return " ".join((name or "").split()).lower()


async def _write_graph_twin(
    user_id: str, memory_id: str, content: str, kind: MemoryKind, participants: str,
) -> None:
    """CB2/CB3: mirror an accepted FACT/ASSUMPTION/DECISION memory onto the
    knowledge web. Best-effort, annotation-only — same discipline as
    `_maybe_mark_superseded`: the memory itself already persisted successfully
    before this runs, and any fault here (extraction or graph write) must
    never surface into the write that triggered it.

    DECISION and FACT both assert (CB4: a decision is itself an asserted
    claim, the same epistemic weight as a source-backed fact) so both become
    a FACT node; ASSUMPTION — inferential by nature — becomes a CLAIM node.
    Fusion is one-directional (Option B, ratified): the graph node carries
    `vector_id` = memory_id; `MemoryItem` itself stays untouched.

    Node ids are minted here with the exact same `graph_store.node_id(scope,
    natural_key)` formula `GraphManager.write()` uses internally for typed
    nodes — required so the edges built here (which carry raw ids, unlike
    nodes whose id `write()` recomputes from `properties`) actually land on
    the right rows."""
    try:
        extracted = await asyncio.wait_for(
            writer.extract_entities(content), timeout=_GRAPH_TWIN_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort, never affects the write that already landed
        log.warning("graph-twin entity extraction failed: %s", exc)
        return

    scope = GraphScope(user_id=user_id)
    fact_label = NodeLabel.CLAIM if kind == MemoryKind.ASSUMPTION else NodeLabel.FACT
    fact_id = graph_store.node_id(scope, memory_id)
    nodes = [GraphNode(
        node_id=fact_id, label=fact_label, scope=scope,
        properties={"content": content, "vector_id": memory_id},
    )]
    edges: list[GraphEdge] = []

    entity_ids: dict[str, str] = {}
    relates_to_entity_ids: set[str] = set()  # only entities THIS node RELATES_TO (excludes AUTHORED_BY participants) — §3.2's candidate fan-out

    def _entity_node(name: str, entity_type: str) -> str | None:
        canonical = _normalize_entity_name(name)
        if not canonical:
            return None
        eid = entity_ids.get(canonical)
        if eid is None:
            eid = graph_store.node_id(scope, canonical)
            entity_ids[canonical] = eid
            nodes.append(GraphNode(
                node_id=eid, label=NodeLabel.ENTITY, scope=scope,
                properties={"canonical_name": canonical, "entity_type": entity_type or "concept"},
            ))
        return eid

    for e in extracted.entities:
        eid = _entity_node(e.name, e.entity_type)
        if eid is not None:
            edges.append(GraphEdge(src_id=eid, dst_id=fact_id, label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED))
            relates_to_entity_ids.add(eid)

    for rel in extracted.relates:
        a, b = entity_ids.get(_normalize_entity_name(rel.a)), entity_ids.get(_normalize_entity_name(rel.b))
        if a and b and a != b:
            edges.append(GraphEdge(src_id=a, dst_id=b, label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED))

    for name in participants.split(","):
        pid = _entity_node(name, "person")
        if pid is not None:
            edges.append(GraphEdge(src_id=fact_id, dst_id=pid, label=EdgeLabel.AUTHORED_BY, origin=EdgeOrigin.INFERRED))

    try:
        result = await asyncio.wait_for(
            graph_manager.manager.write(scope, nodes, edges), timeout=_GRAPH_TWIN_TIMEOUT_S,
        )
        if result.degraded:
            log.warning("graph-twin write degraded for memory %s: %s", memory_id, result.notes)
    except Exception as exc:  # noqa: BLE001 — best-effort, never affects the write that already landed
        log.warning("graph-twin write failed for memory %s: %s", memory_id, exc)
        return  # nothing landed — nothing to check for contradictions against

    # §3.2: only a CLAIM (ASSUMPTION-kind) can CONTRADICTS — the edge table is
    # homogeneous Claim<->Claim (knowledge_store.py), and a FACT/DECISION is
    # asserted, not the kind of thing this judge is scoped to weigh in on.
    if fact_label == NodeLabel.CLAIM and relates_to_entity_ids:
        try:
            contradiction_edges = await asyncio.wait_for(
                _judge_contradictions(scope, fact_id, relates_to_entity_ids, content),
                timeout=_GRAPH_TWIN_TIMEOUT_S,
            )
            if contradiction_edges:
                write_result = await asyncio.wait_for(
                    graph_manager.manager.write(scope, [], contradiction_edges), timeout=_GRAPH_TWIN_TIMEOUT_S,
                )
                if write_result.degraded:
                    log.warning("contradiction-edge write degraded for memory %s: %s", memory_id, write_result.notes)
        except Exception as exc:  # noqa: BLE001 — best-effort, never affects the graph twin that already landed
            log.warning("contradiction check failed for memory %s: %s", memory_id, exc)


async def _judge_contradictions(
    scope: GraphScope, fact_id: str, entity_ids: set[str], content: str,
) -> list[GraphEdge]:
    """§3.2: the CONTRADICTS candidate band is 'shares an ENTITY' — never an
    all-pairs compare, same funnel discipline as EB1's supersession candidate
    search. Every existing CLAIM connected (via RELATES_TO) to any of
    `entity_ids` that the just-written CLAIM (`fact_id`) also connects to is a
    candidate; bounded to `_MAX_CONTRADICTION_CANDIDATES` judge calls
    regardless of how many claims share the entity. One candidate's fault is
    logged and skipped, never stopping the rest — the caller applies the
    overall timeout."""
    claim_result = await graph_manager.manager.members(scope, NodeLabel.CLAIM)
    claim_by_id = {n.node_id: n for n in claim_result.nodes if n.node_id != fact_id}
    if not claim_by_id:
        return []

    candidates: set[str] = set()
    for entity_id in entity_ids:
        edges_result = await graph_manager.manager.edges_of(scope, entity_id, EdgeLabel.RELATES_TO)
        for e in edges_result.edges:
            other = e.dst_id if e.src_id == entity_id else e.src_id
            if other in claim_by_id:
                candidates.add(other)

    new_edges: list[GraphEdge] = []
    for candidate_id in list(candidates)[:_MAX_CONTRADICTION_CANDIDATES]:
        existing_content = claim_by_id[candidate_id].properties.get("content", "")
        try:
            contradicts = await writer.judge_contradiction(content, existing_content)
        except Exception as exc:  # noqa: BLE001 — one candidate's fault must not skip the rest
            log.warning("contradiction judgment failed for %s: %s", candidate_id, exc)
            continue
        if contradicts:
            new_edges.append(GraphEdge(
                src_id=fact_id, dst_id=candidate_id, label=EdgeLabel.CONTRADICTS, origin=EdgeOrigin.INFERRED,
            ))
    return new_edges


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
