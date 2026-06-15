# core/memory/ — the sole MemoryPort implementer (4 Qdrant tiers)

Owns hydration and the write policy behind `foundation.MemoryPort`: wiki, semantic,
episodic, procedural — ranked by trust + recency, budgeted with a Lagrangian
(water-filling) allocation.

## NEVER
- The `user_id` payload filter is MANDATORY and FAIL-CLOSED: no `user_id` ⇒ no
  memory (hydrate returns an empty package; write is a no-op). No other module may
  construct a raw Qdrant / `store` query — this Manager is the only door
  (invariant §V.20, ADR 0002).
- Experts/orchestrator only PROPOSE writes; they never write memory directly
  (§I.6). WIKI is user-authored only — a write proposal targeting WIKI is redirected
  to SEMANTIC; WORKING never persists.
- Every fault DEGRADES, never fails the run: embeddings/store down ⇒ return a
  `degraded` package with an honest note, never raise into a turn. Be honest about
  empty-because-down vs empty-because-no-memory.
- Don't invert trust ordering: WIKI highest (`_TIER_TRUST`); semantic/procedural
  writes gate on `_MIN_ACCEPT_CONFIDENCE`.

## Honest enforcement status
Runtime `user_id` scoping is enforced AND tested (`tests/memory_isolation.py`).
The Semgrep **build-gate** meant to block unscoped queries is documented but
**NOT built yet** (`docs/architecture/INVARIANT_OWNERSHIP.md` §V.20) — don't assume
CI catches an unscoped query; the single-door rule is the real guard today.

## Conventions
- `manager.py` is the door (implements `hydrate` + `record_write_proposals`);
  `store.py` (Qdrant), `embeddings.py` (nomic, 768-dim), `writer.py` (distillation)
  are internals. `learn()` is the background memory-agent (best-effort, off the hot
  path). `memory` prompt is unlocked.

## Tests
`tests/memory_isolation.py`, `tests/memory_tools.py`, `tests/memory_wiki_and_learn.py`.

## Authoritative docs
`core/memory/ARCHITECTURE.md`, `docs/architecture/memory/README.md`, ADR
`docs/decisions/accepted/0002-single-qdrant-userid-scoping.md`.
