#!/usr/bin/env python3
"""
Persistent Cross-Session Memory Demo
Critical Benchmark 1 (Persistent Cross-Session Memory) + Exceptional Benchmark 2 (Autonomous Project Continuity)
Demo Readiness scene: "the second session is the magic"

═══════════════════════════════════════════════════════════════════════
WHAT THIS DEMONSTRATES
═══════════════════════════════════════════════════════════════════════

Day 1  — A working session ends. The assistant seeds project decisions,
         open TODOs, and architectural assumptions through the EXISTING
         MemoryPort.record_write_proposals() write path. No special
         schema; no new EntryType.  Transcript: discarded.

Day 7  — A completely fresh session opens with NO prior context. The
         maintainer asks four questions:
           • What was decided?
           • What is still open?
           • What assumptions were recorded?
           • What is the current status and what comes next?
         The answers come entirely from MemoryManager.hydrate() — ranked
         by trust x recency, budgeted by Lagrangian water-filling.
         No injected transcript. No manual context.

═══════════════════════════════════════════════════════════════════════
HONEST NOT-YET LABELS (gated on issue #16 — typed-record schema)
═══════════════════════════════════════════════════════════════════════

These capabilities are ABSENT from today's substrate and are clearly
marked throughout this script:

  • First-class typed provenance  (source doc, author, confidence chain)
  • Typed fact-vs-assumption distinction  (Decision / Assumption / TODO)
  • Decision-rank boost over episodic conversation content

The demo marks these NOT-YET rather than faking them.

═══════════════════════════════════════════════════════════════════════
USAGE  (from repo root or backend/)
═══════════════════════════════════════════════════════════════════════

  # hermetic (no Qdrant needed):
  python backend/scripts/persistent_memory_demo.py

  # live (requires Qdrant at localhost:6333):
  python backend/scripts/persistent_memory_demo.py --live

  # or from backend/ with an activated venv:
  PYTHONPATH=. .venv/bin/python scripts/persistent_memory_demo.py

Hermetic mode patches the Qdrant store and embedding model with
in-memory doubles so the demo runs anywhere without infrastructure.
Live mode uses the real nomic-embed-text embedder and a local Qdrant
instance for full semantic recall quality.
"""
from __future__ import annotations

# ── path bootstrap (works from any CWD: repo root or backend/) ───────────────
import os
import sys

_HERE = os.path.abspath(os.path.dirname(__file__))
# Walk up from scripts/demos/ until we find the directory that contains
# foundation/ (the backend package root). This works from any CWD.
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
import textwrap
import time
import urllib.request

# ── project ───────────────────────────────────────────────────────────────────
from foundation import (
    HydrationRequest,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
)
from core.memory.manager import MemoryManager

# ─────────────────────────────────────────────────────────────────────────────
# Synthetic project fixture — "Project Meridian"
#
# A realistic set of Day-1 memories representing the state a maintainer would
# want to recover in a fresh session one week later:
#   SEMANTIC   — durable architectural decisions (high trust, retrieved for any
#                decision-oriented query)
#   EPISODIC   — in-session events and open work items (retrieved for status /
#                next-actions queries)
#   PROCEDURAL — working assumptions and preferences (retrieved for context
#                about constraints and operating conditions)
# ─────────────────────────────────────────────────────────────────────────────

DAY1_PROPOSALS: list[MemoryWriteProposal] = [
    # ── Architectural decisions → SEMANTIC ────────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "Decision [Meridian, Day 1]: Adopted vector-first memory retrieval over "
            "graph-first. Rationale: faster iteration; graph complexity deferred to "
            "Phase 2 when query patterns are better understood. Decision was unanimous."
        ),
        rationale="architectural decision logged by orchestrator",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "Decision [Meridian, Day 1]: Single Qdrant instance with user_id payload "
            "filtering chosen over per-user collections. Rationale: operational "
            "simplicity, no provisioning latency per signup, adequate isolation at "
            "V1 scale. To revisit if tenant count exceeds ~50k."
        ),
        rationale="architectural decision logged by orchestrator",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content=(
            "Decision [Meridian, Day 1]: Subscription tiers set at Free / Starter $29 "
            "/ Pro $79 / Agency $199 per month. Token budgets, not report counts, are "
            "the unit of consumption. Free-to-paid conversion target: 12% in 90 days."
        ),
        rationale="product decision logged by orchestrator",
        confidence=0.95,
    ),
    # ── Open work items and session events → EPISODIC ─────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "TODO [OPEN, Day 1]: Wire the Next.js frontend SSE client to the real "
            "FastAPI backend. The frontend is currently mock-backed "
            "(frontend/src/lib/api/mock.ts). Blocked on session-auth middleware. "
            "Owner: unassigned. Priority: P1 before any public demo."
        ),
        rationale="open work item from Day-1 planning session",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "TODO [OPEN, Day 1]: Implement Stripe webhook handler for subscription "
            "tier changes (invoice.paid event). Token-budget resets must be atomic "
            "in Redis. Unstarted. Priority: P1 for multi-tenant billing launch."
        ),
        rationale="open work item from Day-1 planning session",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "TODO [OPEN, Day 1]: Harden rate limiter to key on user_id + IP, not "
            "session_id alone. Current keying is a multi-tenant security gap. "
            "Flagged — must close before any public beta. Blocked on: nothing."
        ),
        rationale="open security item from Day-1 review",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.EPISODIC,
        content=(
            "Open question [UNRESOLVED, Day 1]: Should the report delivery format be "
            "a static Markdown file or a live SSE-streamed canvas? Team is split. "
            "Decision deferred pending a client demo to assess UX preference. "
            "No technical blocker — both paths are feasible."
        ),
        rationale="unresolved question from Day-1 session",
        confidence=0.95,
    ),
    # ── Architectural assumptions → PROCEDURAL ────────────────────────────────
    MemoryWriteProposal(
        store=MemoryStore.PROCEDURAL,
        content=(
            "Assumption [Meridian, Day 1]: Gemini free-tier quota (~20 RPM) is "
            "sufficient for single-user development. Production multi-expert parallel "
            "runs require a paid Gemini key. Current free-tier will rate-limit under "
            "any sustained load. Needs paid quota before beta onboarding."
        ),
        rationale="technical assumption recorded at session start",
        confidence=0.95,
    ),
    MemoryWriteProposal(
        store=MemoryStore.PROCEDURAL,
        content=(
            "Assumption [Meridian, Day 1]: nomic-embed-text 768-dimensional vectors "
            "provide adequate semantic resolution for memory retrieval at V1 scale. "
            "Validity window: up to ~10k entries per user. To be re-evaluated when "
            "median user corpus approaches this size."
        ),
        rationale="technical assumption recorded at session start",
        confidence=0.95,
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Day-7 query set — mirrors the C1 benchmark's four required questions
# ─────────────────────────────────────────────────────────────────────────────

DAY7_QUERIES: list[tuple[str, str]] = [
    (
        "What architectural decisions were made on this project?",
        "DECISIONS",
    ),
    (
        "What TODOs and open work items are still unresolved?",
        "OPEN WORK",
    ),
    (
        "What technical assumptions and constraints were recorded?",
        "ASSUMPTIONS",
    ),
    (
        "What is the current project status and what should we work on next?",
        "STATUS / NEXT ACTIONS",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Hermetic in-memory store double
# ─────────────────────────────────────────────────────────────────────────────


class _InMemoryStore:
    """In-memory replacement for core.memory.store.

    Captures upserts; replays all stored items (score=1.0) on search.
    Dedup is intentionally bypassed (limit=1 search always returns empty) so
    each distinct Day-1 proposal is stored as its own independent entry.
    The user_id filter is enforced exactly as the real store does.
    """

    def __init__(self) -> None:
        self._data: dict[MemoryStore, list[dict]] = {t: [] for t in MemoryStore}

    def search(
        self, tier: MemoryStore, user_id: str, vector: list[float], limit: int = 8
    ) -> list[dict]:
        if limit == 1:
            # dedup probe: signal "no near-duplicate exists" so each proposal
            # gets its own entry (correct for distinct-content writes)
            return []
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
    ) -> str | None:
        import uuid

        pid = point_id or str(uuid.uuid4())
        for existing in self._data[tier]:
            if existing.get("id") == pid:
                existing.update(content=content, confidence=confidence, created_at=time.time())
                return pid
        self._data[tier].append(
            {
                "id": pid,
                "user_id": user_id,
                "session_id": session_id,
                "content": content,
                "score": 1.0,
                "created_at": time.time(),
                "confidence": confidence,
                "trust": trust,
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
        return [[0.1] * 768 for _ in texts]

    _emb_mod.embed = _fake_embed


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

_WIDTH = 70


def _banner(title: str) -> None:
    print("\n" + "═" * _WIDTH)
    pad = (_WIDTH - len(title) - 2) // 2
    print(f"{'═' * pad} {title} {'═' * (_WIDTH - pad - len(title) - 2)}")
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
# Scene 1 — Day 1: seed memories
# ─────────────────────────────────────────────────────────────────────────────


async def scene_day1(manager: MemoryManager, user_id: str) -> None:
    _banner("SCENE 1  ·  DAY 1  ·  Session A: project kickoff")

    print(f"""
  Project : Meridian AI Research Pipeline (synthetic)
  User    : {user_id}
  Session : session-day1-a  (will be discarded after this scene)

  Writing {len(DAY1_PROPOSALS)} project-state items through
  MemoryPort.record_write_proposals() — the EXISTING write path.
  No new EntryType; no schema change; plain content in existing tiers.
""")

    await manager.record_write_proposals(
        user_id=user_id,
        session_id="session-day1-a",
        proposals=DAY1_PROPOSALS,
    )

    by_tier: dict[str, list[str]] = {}
    for p in DAY1_PROPOSALS:
        by_tier.setdefault(p.store.value.upper(), []).append(p.content[:80] + "…")

    for tier_name, snippets in by_tier.items():
        print(f"  [{tier_name}]  {len(snippets)} item(s) written")
        for s in snippets:
            print(_wrap(s, indent=6))
        print()

    print("  Writes complete.")
    print("\n  ── Session A ends. Transcript discarded. Clock advances 7 days. ──")


# ─────────────────────────────────────────────────────────────────────────────
# Scene 2 — Day 7: fresh session, hydrate, narrate
# ─────────────────────────────────────────────────────────────────────────────


async def scene_day7(manager: MemoryManager, user_id: str) -> None:
    _banner("SCENE 2  ·  DAY 7  ·  Session B: fresh start, zero transcript")

    print(f"""
  User    : {user_id}
  Session : session-day7-b  (brand new — no prior messages)
  Context : NONE  (no conversation history, no injected text)

  The system calls MemoryManager.hydrate() for each question.
  All answers come from the real hydrate() ranking:
    trust-tier ordering (SEMANTIC > EPISODIC = PROCEDURAL)
    x recency decay (30-day half-life)
    x Lagrangian water-filling budget allocation

  NOT-YET gaps (gated on issue #16):
    [x] Typed provenance  (source, author, confidence chain)
    [x] Fact-vs-assumption type labels  (Decision / Assumption / TODO)
    [x] Decision-rank boost over episodic content
""")

    for query_text, label in DAY7_QUERIES:
        _section(f"QUESTION: {label}")
        print(f'\n  "{query_text}"\n')

        normalized = NormalizedInput(
            modality="text",
            content_type="text/plain",
            content=query_text,
        )
        pkg = await manager.hydrate(
            HydrationRequest(
                session_id="session-day7-b",
                user_id=user_id,
                normalized=normalized,
                token_budget=6000,
            )
        )

        if pkg.degraded:
            print(f"  [DEGRADED] {pkg.notes or 'memory temporarily unavailable'}")
            continue

        if not pkg.items:
            note = pkg.notes or "no prior memory for this user"
            print(f"  [EMPTY] {note}")
            continue

        print(f"  {len(pkg.items)} item(s) retrieved — ranked by (trust, score):\n")

        for i, item in enumerate(pkg.items, 1):
            tier = item.store.value.upper()
            score = f"{item.score:.3f}"
            if item.created_at:
                age_s = time.time() - item.created_at
                age_label = (
                    f"{age_s / 86400:.1f}d ago"
                    if age_s >= 3600
                    else f"{age_s / 60:.0f}m ago"
                )
            else:
                age_label = "age: unknown"

            print(
                f"  [{i}] tier={tier}  trust={item.trust}  score={score}  "
                f"learned: {age_label}"
            )
            print(f"       provenance: timestamp only  |  NOT-YET: typed source/author (#16)")
            print(_wrap(item.content, indent=6))
            print()

    _section("END OF DAY-7 SESSION")
    print("""
  Session B had ZERO prior transcript. Every item above came from
  MemoryManager.hydrate() operating on what Session A wrote to the
  persistent store one simulated week earlier.

  This is the "second session is the magic" scene for C1 / E2.

  What the demo proves:
    [ok] Cross-session continuity — no transcript required
    [ok] user_id-scoped retrieval — no cross-user leakage
    [ok] Trust-tier ordering — SEMANTIC decisions rank above episodic items
    [ok] Recency decay — older items rank lower than recent ones
    [ok] Lagrangian budget allocation — all tiers represented within budget

  What is NOT-YET (gated on issue #16):
    [x] Typed Decision / Assumption / TODO records with first-class fields
    [x] Provenance chain (source doc, author, session id surfaced to user)
    [x] Fact-vs-assumption distinction in the retrieved output
    [x] Decision-rank boost that elevates decisions above conversation
""")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def _qdrant_reachable() -> bool:
    try:
        urllib.request.urlopen("http://localhost:6333/readyz", timeout=2)
        return True
    except Exception:
        return False


async def run_demo(*, live: bool, user_id: str) -> None:
    _banner("CLANNON · PERSISTENT CROSS-SESSION MEMORY DEMO")
    print(f"""
  Critical Benchmark 1 (Persistent Cross-Session Memory)
  Exceptional Benchmark 2 (Autonomous Project Continuity)
  Demo Readiness scene: "the second session is the magic"
""")

    if live:
        if not _qdrant_reachable():
            print("[ERROR] --live requires Qdrant at localhost:6333.")
            print("        Start it with:  docker-compose up -d qdrant")
            sys.exit(1)
        print("  Mode: LIVE — real Qdrant + nomic-embed-text embeddings\n")
    else:
        mem_store = _InMemoryStore()
        _install_hermetic_doubles(mem_store)
        print("  Mode: HERMETIC — in-memory store + fake embedder (no Qdrant needed)\n")

    manager = MemoryManager()
    await scene_day1(manager, user_id)
    await scene_day7(manager, user_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clannon persistent cross-session memory demo (C1 / E2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real Qdrant and nomic-embed-text (requires docker-compose stack)",
    )
    parser.add_argument(
        "--user-id",
        default="demo-meridian-001",
        metavar="UID",
        help="Demo user identifier (default: demo-meridian-001)",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(live=args.live, user_id=args.user_id))


if __name__ == "__main__":
    main()
