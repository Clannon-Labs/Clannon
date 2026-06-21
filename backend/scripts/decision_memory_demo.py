#!/usr/bin/env python3
"""
Institutional Decision Memory Demo
Critical Benchmark 4 (Institutional Decision Memory) · Demo Readiness scene

═══════════════════════════════════════════════════════════════════════
WHAT THIS DEMONSTRATES
═══════════════════════════════════════════════════════════════════════

Session A  — An architectural debate is in progress: vector-first vs
             graph-first retrieval for Clannon's memory layer. Three
             participants propose, argue, and reach a decision. The
             outcome, arguments, risks, and participant roles are seeded
             through the EXISTING MemoryPort.record_write_proposals()
             write path using structured content in existing metadata
             fields. No new EntryType; no schema change.
             Transcript: discarded at session end.

Weeks later — A fresh session opens with NO prior context: no transcript,
              no injected text. Four questions from the C4 benchmark are
              posed via MemoryManager.hydrate():
                1. Why was Option B (graph-first) selected?
                2. What arguments supported it?
                3. What risks were identified?
                4. Who proposed the decision and who participated?

              All answers come from the real hydrate() ranking:
                trust-tier ordering  (SEMANTIC > EPISODIC = PROCEDURAL)
                × recency decay      (30-day half-life)
                × Lagrangian water-filling budget allocation

═══════════════════════════════════════════════════════════════════════
HONEST NOT-YET LABELS (gated on issue #16 — typed-record schema)
═══════════════════════════════════════════════════════════════════════

These capabilities are ABSENT from today's substrate and are clearly
marked throughout this script:

  • First-class typed Decision artifact  (EntryType.DECISION — no such
    type exists; entries are tier-classified untyped blobs)
  • Decision-outranks-conversation ranking boost  (no per-record rank
    boost exists; SEMANTIC trust=2 already outranks EPISODIC trust=1,
    but a *decision* in SEMANTIC does not outrank a *factual* SEMANTIC
    entry — #16 would add a per-entry priority field)
  • Structured alternatives list / risk matrix   (not a MemoryItem field)
  • Participant identity  (no author/proposer field on MemoryItem)

The demo marks these NOT-YET rather than faking them.

═══════════════════════════════════════════════════════════════════════
USAGE  (from repo root or backend/)
═══════════════════════════════════════════════════════════════════════

  # hermetic (no Qdrant or embedding model needed):
  python backend/scripts/decision_memory_demo.py

  # live (requires Qdrant at localhost:6333):
  python backend/scripts/decision_memory_demo.py --live

  # or from backend/ with an activated venv:
  PYTHONPATH=. .venv/bin/python scripts/decision_memory_demo.py

Hermetic mode patches the Qdrant store and embedding model with
in-memory doubles so the demo runs anywhere without infrastructure.
Debate items are backdated 3 weeks in hermetic mode so the age labels
and recency-decay scores are truthful. Live mode uses the real
nomic-embed-text embedder and a local Qdrant instance.
"""
from __future__ import annotations

# ── path bootstrap (works from any CWD: repo root or backend/) ───────────────
import os
import sys

_HERE = os.path.abspath(os.path.dirname(__file__))
_BACKEND = _HERE
while _BACKEND != os.path.dirname(_BACKEND):
    if os.path.isdir(os.path.join(_BACKEND, "foundation")):
        break
    _BACKEND = os.path.dirname(_BACKEND)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# ── stdlib ────────────────────────────────────────────────────────────────────
import argparse
import asyncio
import math
import re
import textwrap
import time
import urllib.request
import uuid

# ── project ───────────────────────────────────────────────────────────────────
from foundation import (
    HydrationRequest,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
)
from core.memory.manager import MemoryManager

# ─────────────────────────────────────────────────────────────────────────────
# Synthetic debate fixture — "Project Clannon · Retrieval Architecture Debate"
#
# The scenario: three weeks ago, Clannon's team debated whether to build the
# memory retrieval layer around vectors (Option A) or a knowledge graph
# (Option B). After deliberation, Option B (graph-first) was chosen for its
# structural reasoning advantage, subject to the typed-record schema (issue #16)
# being ratified first. This fixture captures the full debate record.
#
# Encoding strategy: all decision structure (outcome, arguments, risks,
# participants) lives in the content field as human-readable structured text.
# The rationale field carries a category label. No new metadata fields are
# introduced — this is the EXISTING write path exactly as designed.
#
# Tiers used:
#   SEMANTIC   — the decision outcome, the argument record, the risk register
#                (high trust=2; retrieved for any decision-oriented query)
#   EPISODIC   — who said what; the deliberation timeline and trigger context
#                (trust=1; retrieved for participant and context queries)
#   PROCEDURAL — the operational constraint this decision places on future work
#                (trust=1; retrieved for "what are we bound by?" queries)
# ─────────────────────────────────────────────────────────────────────────────

_THREE_WEEKS_S = 21 * 86_400  # seconds in 3 weeks

DEBATE_PROPOSALS: list[MemoryWriteProposal] = [
    # ── Decision outcome → SEMANTIC ───────────────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "DECISION [Clannon · Retrieval Architecture, Week-3]: "
            "Option B (graph-first retrieval) was SELECTED over Option A "
            "(vector-first retrieval) for the long-term memory retrieval layer. "
            "Outcome: unanimous after deliberation. "
            "Rationale: structural reasoning over decision relationships "
            "is the primary use-case; vector similarity alone cannot express "
            "'what decisions depend on this assumption?' chains. "
            "Effective from: this debate session. "
            "Caveat: implementation gated on ratification of typed-record schema "
            "(issue #16) — the substrate to write typed Decision artifacts does "
            "not exist yet. Until #16 lands, entries remain untyped tier blobs "
            "and no decision-rank boost is applied."
        ),
        rationale="decision outcome — architectural debate",
        confidence=0.97,
    ),
    # ── Arguments supporting Option B → SEMANTIC ─────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "ARGUMENTS FOR Option B (graph-first) [Clannon · Retrieval Architecture, Week-3]: "
            "1. Semantic relationships matter more than proximity for institutional memory: "
            "a decision record is linked to the assumptions it rests on and the risks it "
            "accepted, not just textually similar to them. "
            "2. Multi-hop reasoning: graph traversal enables 'which decisions become "
            "questionable if assumption X is invalidated?' — a query vector similarity "
            "cannot answer. "
            "3. Provenance chains: when typed Decision artifacts (#16) land, graph edges "
            "directly encode 'ratified by / proposed by / supersedes' without needing "
            "post-hoc reconstruction from content text. "
            "4. Strategic alignment: the 12-month roadmap includes cross-media knowledge "
            "graph (ADR 0005) and repository intelligence (ADR 0008) — both are natively "
            "graph-shaped; a graph-first retrieval layer amortises that investment."
        ),
        rationale="arguments for winning option — architectural debate",
        confidence=0.95,
    ),
    # ── Arguments for rejected Option A → SEMANTIC ───────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "ARGUMENTS FOR Option A (vector-first, REJECTED) [Clannon · Retrieval Architecture, Week-3]: "
            "1. Lower implementation complexity: Qdrant + nomic-embed-text is already "
            "built and end-to-end proven on the happy path (~38s grounded report). "
            "2. Faster iteration: no graph DB to provision, no schema to agree on. "
            "3. Adequate for V1 semantic similarity queries (factual recall, context "
            "injection). Counter-argument that carried the vote: V1 adequacy was "
            "accepted but the cost of migrating away from vector-only at V2 "
            "was judged higher than the cost of deferring graph implementation "
            "until #16 is ratified."
        ),
        rationale="arguments for rejected option — architectural debate",
        confidence=0.95,
    ),
    # ── Risk register → SEMANTIC ──────────────────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "RISKS IDENTIFIED for Option B (graph-first) [Clannon · Retrieval Architecture, Week-3]: "
            "R1 [HIGH] Implementation complexity: graph DB (e.g. Neo4j or Qdrant sparse "
            "graphs) requires expertise the team does not yet have. Mitigation: spike on "
            "Qdrant sparse-vector hybrid before committing to a dedicated graph DB. "
            "R2 [MEDIUM] Schema migration cost: existing episodic/semantic blobs must be "
            "re-indexed when typed records (#16) arrive. Mitigation: design the typed "
            "schema to be additive (new payload fields, not a collection replacement). "
            "R3 [MEDIUM] Query latency: graph traversal is O(depth) vs O(1) ANN; "
            "hybrid retrieval (vector ANN for candidates + graph for re-ranking) "
            "is the planned mitigation. "
            "R4 [LOW] Vendor lock-in: if graph traversal requires Neo4j, operational "
            "overhead increases. Mitigation: prefer graph-capable vector DBs first."
        ),
        rationale="risk register — architectural debate",
        confidence=0.95,
    ),
    # ── Participant record → EPISODIC ─────────────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "PARTICIPANTS [Clannon · Retrieval Architecture, Week-3]: "
            "Alex (Architect) — proposed Option B; primary argument: "
            "'vector proximity answers what is similar, not what depends on what.' "
            "Sam (Research Lead) — initially proposed Option A citing implementation "
            "speed; changed position after the multi-hop reasoning argument "
            "(R: 'if assumption X is invalidated, which decisions fall?'). "
            "Jordan (CTO) — facilitated; cast the deciding voice citing 12-month "
            "strategic alignment with the knowledge graph roadmap. "
            "Decision reached by consensus after Sam's position shift. "
            "NOT-YET: no author/proposer field on MemoryItem (#16 would add one)."
        ),
        rationale="participant roles — architectural debate",
        confidence=0.95,
    ),
    # ── Deliberation context → EPISODIC ──────────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "DELIBERATION CONTEXT [Clannon · Retrieval Architecture, Week-3]: "
            "Trigger: memory hydration tests confirmed vector retrieval works for "
            "factual recall but returned semantically adjacent (not causally linked) "
            "items when querying 'why was X decided'. The gap exposed a structural "
            "limit of cosine-similarity ranking for decision-memory use-cases. "
            "Duration: one 2-hour async discussion thread. "
            "Reference material: ADR 0002 (single-Qdrant user_id scoping), "
            "issue #16 (typed-record schema proposal), ARCHITECTURE.md §4 (memory tiers). "
            "Next step: spike on Qdrant sparse-vector hybrid retrieval to validate "
            "feasibility before architectural commitment."
        ),
        rationale="deliberation context — architectural debate",
        confidence=0.90,
    ),
    # ── Operating constraint → PROCEDURAL ────────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.PROCEDURAL,
        content=(
            "CONSTRAINT [post-debate, Week-3]: Any new memory retrieval design must "
            "account for graph-first retrieval as the ratified long-term direction. "
            "Interim vector-only implementation (existing Qdrant store) is explicitly "
            "a bridge, not a destination. No new code that deepens vector-only coupling "
            "should be merged without a migration path noted in the PR. "
            "Full graph implementation is gated on #16 (typed-record schema ratification) "
            "and a technology spike validating graph DB choice."
        ),
        rationale="operating constraint — post-decision",
        confidence=0.92,
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# C4 benchmark query set — the four retrievable questions
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARK_QUERIES: list[tuple[str, str]] = [
    (
        "Why was Option B (graph-first retrieval) selected over Option A?",
        "DECISION OUTCOME · why Option B",
    ),
    (
        "What arguments supported graph-first retrieval?",
        "ARGUMENTS · supporting Option B",
    ),
    (
        "What risks were identified during the retrieval architecture debate?",
        "RISK REGISTER · identified risks",
    ),
    (
        "Who proposed the graph-first decision and who participated in the debate?",
        "PARTICIPANTS · who proposed / who participated",
    ),
]

# The capability gaps that require typed-record schema (#16).
# Listed here so the demo maps 1-to-1 against the full benchmark spec while
# being honest about what the current substrate cannot do.
NOT_YET_CAPABILITIES: list[str] = [
    "First-class typed Decision artifact  (EntryType.DECISION — gated on #16)",
    "Decision-outranks-conversation ranking boost  (per-entry priority field — gated on #16)",
    "Structured alternatives list as a native field on MemoryItem  (gated on #16)",
    "Participant identity as a typed author/proposer field on MemoryItem  (gated on #16)",
    "Temporal truth — 'was this decision superseded?' / is-valid-at  (gated on #16)",
]

# ─────────────────────────────────────────────────────────────────────────────
# Hermetic helpers — deterministic BOW hash embedding + cosine similarity
#
# The real nomic-embed-text model is replaced with a bag-of-words hashed
# vector so the hermetic mode runs without any ML infrastructure. Each text
# maps to a 768-dim vector where hash(token) % 768 accumulates token counts,
# then L2-normalised. Cosine similarity between query and stored vectors is
# proportional to token overlap — enough to prove per-question ranking:
#   "why selected?"    → DECISION record ranks first (shares "selected", "decision")
#   "what arguments?"  → ARGUMENTS FOR B ranks first (most "graph" occurrences)
#   "what risks?"      → RISKS record ranks first (shares "risks", "r1", "r2"…)
#   "who participated?"→ PARTICIPANTS leads its tier (shares "proposed", "participants")
# Scores remain above the manager's _RELEVANCE_FLOOR (0.30) for matching items.
# ─────────────────────────────────────────────────────────────────────────────


_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "not", "in", "on", "at", "to", "of",
    "for", "is", "it", "its", "be", "as", "by", "this", "that", "was",
    "are", "were", "has", "have", "had", "with", "from", "will", "would",
    "can", "do", "did", "but", "if", "so", "all", "we", "i", "you", "he",
    "she", "they", "what", "which", "who", "how", "when", "where", "why",
})


def _bow_embed(text: str, dim: int = 65536) -> list[float]:
    """Deterministic BOW hash embedding with stop-word filtering.

    dim=65536 reduces hash-collision probability to ~0.05% per token-pair
    so different tokens virtually never share a slot — making the
    query-normalized overlap score in _InMemoryStore.search accurate and
    predictable. Stop words are excluded so discriminating content terms
    drive similarity. Scores reliably exceed the manager's _RELEVANCE_FLOOR
    (0.30) for topically matching items and rank correctly across all four
    C4 benchmark questions.
    """
    vec = [0.0] * dim
    for token in re.findall(r"[a-z0-9#]+", text.lower()):
        if token in _STOP_WORDS or len(token) == 1:
            continue
        idx = hash(token) % dim
        if idx < 0:
            idx += dim
        vec[idx] += 1.0
    mag = math.sqrt(sum(v * v for v in vec))
    return [v / mag for v in vec] if mag else [1.0 / math.sqrt(dim)] * dim


# ─────────────────────────────────────────────────────────────────────────────
# Hermetic in-memory store double
# ─────────────────────────────────────────────────────────────────────────────


class _InMemoryStore:
    """In-memory replacement for core.memory.store.

    Captures upserts; replays all stored items (score=1.0) on search.
    Dedup is bypassed (limit=1 search always returns empty) so each distinct
    proposal gets its own independent entry. The user_id filter is enforced
    exactly as the real store does.

    created_at_offset: seconds added to time.time() on every upsert. Pass a
    negative value to backdate items (e.g. -21*86400 for "3 weeks ago"). Reset
    to 0.0 before writing items that should carry the current timestamp.
    """

    def __init__(self, created_at_offset: float = 0.0) -> None:
        self._data: dict[MemoryStore, list[dict]] = {t: [] for t in MemoryStore}
        self.created_at_offset = created_at_offset
        # Freeze "now" so every upserted item shares the same created_at.
        # Sequential upserts would otherwise produce microsecond-newer
        # timestamps for later items, breaking tie-breaking by insertion order.
        self._frozen_now = time.time()

    def search(
        self, tier: MemoryStore, user_id: str, vector: list[float], limit: int = 8
    ) -> list[dict]:
        if limit == 1:
            # dedup probe: signal "no near-duplicate" so each distinct proposal
            # lands as its own entry (correct for distinct-content writes)
            return []
        q_dims = frozenset(i for i, v in enumerate(vector) if v > 0.0)
        results = []
        for item in self._data[tier]:
            if item.get("user_id") != user_id:
                continue
            stored = item.get("vector")
            if stored and q_dims:
                d_dims = frozenset(i for i, v in enumerate(stored) if v > 0.0)
                score = len(q_dims & d_dims) / len(q_dims)
            else:
                score = 1.0
            results.append({**item, "score": score})
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

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
    ) -> str | None:
        pid = point_id or str(uuid.uuid4())
        created_at = self._frozen_now + self.created_at_offset
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
                "vector": list(vector),
            }
        )
        return pid

    def is_down(self) -> bool:
        return False


def _install_hermetic_doubles(mem_store: _InMemoryStore) -> None:
    """Replace Qdrant store and embedding model with the in-memory doubles."""
    import core.memory.embeddings as _emb_mod
    import core.memory.store as _store_mod

    _store_mod.search = mem_store.search
    _store_mod.upsert = mem_store.upsert
    _store_mod.is_down = mem_store.is_down

    async def _fake_embed(texts: list[str]) -> list[list[float]] | None:
        return [_bow_embed(t) for t in texts]

    _emb_mod.embed = _fake_embed


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

_WIDTH = 72


def _banner(title: str) -> None:
    print("\n" + "═" * _WIDTH)
    pad = (_WIDTH - len(title) - 2) // 2
    remainder = _WIDTH - pad - len(title) - 2
    print(f"{'═' * pad} {title} {'═' * remainder}")
    print("═" * _WIDTH)


def _section(title: str) -> None:
    print(f"\n{'─' * _WIDTH}")
    print(f"  {title}")
    print("─" * _WIDTH)


def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(
        text, width=_WIDTH - indent, initial_indent=prefix, subsequent_indent=prefix
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scene 1 — Debate session: seed the decision record
# ─────────────────────────────────────────────────────────────────────────────


async def scene_debate(manager: MemoryManager, user_id: str) -> None:
    _banner("SCENE 1  ·  WEEK -3  ·  The architectural debate")

    print(f"""
  Scenario : Clannon team debates retrieval architecture.
             Three participants: Alex (Architect), Sam (Research Lead),
             Jordan (CTO). Two options on the table:
               Option A: vector-first retrieval  (existing Qdrant ANN)
               Option B: graph-first retrieval   (structural reasoning)
  User     : {user_id}
  Session  : session-debate  (will be discarded after this scene)

  Writing {len(DEBATE_PROPOSALS)} debate-record items through
  MemoryPort.record_write_proposals() — the EXISTING write path.
  No new EntryType; no schema change; structured content in existing
  metadata fields (content text + rationale label + confidence).
""")

    await manager.record_write_proposals(
        user_id=user_id,
        session_id="session-debate",
        proposals=DEBATE_PROPOSALS,
    )

    by_tier: dict[str, list[str]] = {}
    for p in DEBATE_PROPOSALS:
        by_tier.setdefault(p.store.value.upper(), []).append(
            p.content[:80] + "…"
        )

    for tier_name, snippets in by_tier.items():
        print(f"  [{tier_name}]  {len(snippets)} item(s) written")
        for s in snippets:
            print(_wrap(s, indent=6))
        print()

    print("  Writes complete.")
    print("\n  ── Debate session ends. Transcript discarded. Three weeks pass. ──")


# ─────────────────────────────────────────────────────────────────────────────
# Scene 2 — Weeks later: fresh session, reconstruct the debate via hydrate()
# ─────────────────────────────────────────────────────────────────────────────


async def scene_reconstruction(
    manager: MemoryManager, user_id: str, *, live: bool = False
) -> None:
    _banner("SCENE 2  ·  TODAY  ·  Fresh session — zero transcript")

    # Recency note: in hermetic mode all debate items were backdated 3 weeks so
    # the age labels are honest; in live mode items are written in the same run
    # and will show 0m ago (the recency-decay differential appears only after
    # real elapsed time between sessions).
    recency_note = (
        "Recency: debate items backdated 3 weeks — age labels are honest"
        if not live
        else "Recency: items written this run (0m ago) — differential appears after real elapsed time"
    )
    embed_note = (
        "Embedding: hermetic mode — relevance approximated by deterministic BOW\n"
        "  hash embeddings (token overlap, not semantic distance); ranking is\n"
        "  directionally correct and scores are honest relative comparisons."
        if not live
        else "Embedding: real nomic-embed-text (768-dim) via local fastembed"
    )

    print(f"""
  User     : {user_id}
  Session  : session-reconstruction  (brand new — no prior messages)
  Context  : NONE  (no conversation history, no injected text)
  {recency_note}
  {embed_note}

  The system calls MemoryManager.hydrate() for each C4 benchmark question.
  All answers come from the real hydrate() ranking:
    trust-tier ordering     (SEMANTIC trust=2 > EPISODIC/PROCEDURAL trust=1)
    × recency decay         (30-day half-life, floor 0.5)
    × Lagrangian water-filling budget allocation

  NOT-YET capabilities (gated on issue #16 — typed-record schema):
    [NOT-YET] First-class typed Decision artifact  (EntryType.DECISION)
    [NOT-YET] Decision-outranks-conversation ranking boost  (per-entry priority)
    [NOT-YET] Structured alternatives / risk matrix as native MemoryItem fields
    [NOT-YET] Typed participant / author field on MemoryItem
    [NOT-YET] Temporal truth — 'was this decision superseded?'
""")

    retrieved_any = False

    for query_text, label in BENCHMARK_QUERIES:
        _section(f"C4 QUESTION: {label}")
        print(f'\n  Q: "{query_text}"\n')

        normalized = NormalizedInput(
            modality="text",
            content_type="text/plain",
            content=query_text,
        )
        pkg = await manager.hydrate(
            HydrationRequest(
                session_id="session-reconstruction",
                user_id=user_id,
                normalized=normalized,
                token_budget=8000,
            )
        )

        if pkg.degraded:
            print(f"  [DEGRADED] {pkg.notes or 'memory temporarily unavailable'}")
            continue

        if not pkg.items:
            note = pkg.notes or "no prior memory for this user"
            print(f"  [EMPTY] {note}")
            continue

        retrieved_any = True
        print(f"  Retrieved {len(pkg.items)} item(s) — ranked by (trust, score):\n")

        for i, item in enumerate(pkg.items, 1):
            tier = item.store.value.upper()
            score_str = f"{item.score:.3f}"
            if item.created_at:
                age_s = time.time() - item.created_at
                if age_s >= 86_400:
                    age_label = f"{age_s / 86400:.1f}d ago"
                elif age_s >= 3600:
                    age_label = f"{age_s / 3600:.1f}h ago"
                else:
                    age_label = f"{age_s / 60:.0f}m ago"
            else:
                age_label = "age: unknown"

            print(
                f"  [{i}] tier={tier}  trust={item.trust}  "
                f"score={score_str}  learned: {age_label}"
            )
            print(f"       provenance: tier + timestamp  |  [NOT-YET] typed author/source (#16)")
            print(_wrap(item.content, indent=6))
            print()

    # Honest NOT-YET summary — every gap is explicit, none faked
    _section("HONEST CAPABILITY GAPS  (not faked — gated on #16)")
    print()
    for cap in NOT_YET_CAPABILITIES:
        print(f"  [NOT-YET] {cap}")

    print()
    if retrieved_any:
        print("  DEMO RESULT: decision + reasoning + alternatives + risks + participants")
        print("  reconstructed from real hydrate() with zero injected transcript.")
        print("  The NOT-YET gaps above are the DEPTH the #16 typed-record schema unlocks.")
    else:
        print("  DEMO RESULT: no items retrieved — check store state or --live flag.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

_DEMO_USER = "demo-c4-decision-debate"


def _qdrant_reachable() -> bool:
    try:
        url = os.getenv("QDRANT_URL", "http://localhost:6333") + "/readyz"
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


async def _run(live: bool) -> None:
    _banner("CLANNON  ·  CRITICAL BENCHMARK 4  ·  Institutional Decision Memory")
    print("""
  Scene: "weeks later, why did we decide X?"
  The debate: vector-first vs graph-first retrieval (Option A vs Option B).
  Option B was chosen. The question is whether the full reasoning, arguments,
  risks, and participant record survive the session boundary — reconstructed
  from memory alone, not from the transcript.
""")

    manager = MemoryManager()
    user_id = _DEMO_USER

    if live:
        if not _qdrant_reachable():
            print("  [ERROR] --live requires Qdrant at localhost:6333 (or $QDRANT_URL)")
            sys.exit(1)
        print(f"  Mode : LIVE  (real Qdrant + nomic-embed-text)\n")
        # Clean up any prior run for this demo user so the demo is repeatable
        from core.memory import store as _store_mod
        _store_mod.delete_user(user_id)
    else:
        print(f"  Mode : HERMETIC  (in-memory doubles, no Qdrant needed)\n")
        mem_store = _InMemoryStore(created_at_offset=-_THREE_WEEKS_S)
        _install_hermetic_doubles(mem_store)

    await scene_debate(manager, user_id)

    # Separate scenes with a pause so the output is easy to read in one run.
    print("\n" + "·" * _WIDTH)

    await scene_reconstruction(manager, user_id, live=live)

    if live:
        # Leave the store clean after a live run.
        from core.memory import store as _store_mod  # noqa: F811
        _store_mod.delete_user(user_id)
        print(f"\n  [cleaned up {user_id} from live store]")

    _banner("END  ·  C4 Decision Memory Demo")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clannon C4 Institutional Decision Memory Demo"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real Qdrant + nomic-embed-text instead of hermetic in-memory doubles",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.live))


if __name__ == "__main__":
    main()
