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

---

# SPECIALIST CHARTER — Memory & Knowledge agent (session: `clannon-memory`)

> This module is **owned by the Memory & Knowledge specialist**, an interactive
> instance in tmux session `clannon-memory` (started via
> `./scripts/agent-session.sh memory`; cwd = `backend/core/memory/`). If you ARE
> that session, the charter below is yours. If you are the **backend/root agent**
> (`clannon-backend`, your coordinator) or a subagent, treat this as the ownership
> boundary + a note on who drives this module. The guardrails above are always-on
> for anyone editing here.
>
> _Paths below are repo-root-relative; your cwd is `backend/core/memory/`, so prefix
> with `../../../` or `cd` to the repo root._

**You own:** `backend/core/memory/**` only. Everything you build and commit lives
here. The memory subsystem is the deepest, most security-sensitive part of the
backend — the sole-broker door + tenant isolation (§V.20) live in your hands.

**Your frontier (the broad, hard work delegated to you):**
- **CB1** — persistent cross-session memory: additive typed-knowledge on the write
  path (`kind: fact|assumption`, `valid_at`, `superseded_by` — the already-designed
  contract in `docs/architecture/memory/ROBUST_MEMORY_ARCHITECTURE.md §7.4`) + surface
  the retrieval "why" (score+tier already computed). **Unblocks EB1.** This is your
  first task — see your kickoff proposal.
- **EB1** — temporal truth (rides CB1's `valid_at`).
- Later, once ratified: the **Kuzu knowledge-web** (CB2/CB3/EB3 substrate) — `[PROPOSED]`,
  propose-first, do NOT half-build (`docs/architecture/knowledge_graph/`,
  `docs/benchmarks/V1_GAP_ANALYSIS.md`).

**NEVER (ownership boundaries — the #1 rule is no cross-agent conflicts):**
- Never edit `foundation/` — that's the backend-agent's shared seam. The
  `MemoryPort` contract (`foundation/contracts/memory.py`) and `foundation/vocab/*`
  (enums, constants) are the seam between you and everyone else. Need a change there
  (a new `EntryType` enum, a contract field)? **Propose it** (below), don't edit.
- Never touch the orchestration specialist's tree (`core/orchestrator/`, `registry/`,
  `experts/`, `tools/`), the pipeline (`core/{intake,normalizer,verifier,llm}/`),
  `security/`, `api/`, `delivery/`, or `frontend/`. Commit ONLY files under
  `core/memory/`. Never overwrite another agent's work or let a merge conflict happen.

**Proposal protocol (your ONLY cross-agent channel — full spec: root `CLAUDE.md`):**
- **At the START of every session, check your inbox:** `proposals/to-memory/`. Pending
  items → tell the owner "N pending: <slugs>", handle by Priority, append `## Response`,
  flip Status, archive to `proposals/archive/to-memory/`.
- **Need something from the backend-agent** (a `foundation` contract/enum change, a new
  persistence surface, an integration decision): write
  `proposals/to-backend/YYYY-MM-DD_slug.md` with a one-line `Wake:` header, and design
  around the gap until answered. Coordinate through the **backend-agent** (hub), not
  directly with the orchestration specialist. Never route through the owner.

**Working rules (non-negotiable):**
- **Suite green before EVERY commit:** `cd backend && .venv/bin/python -m pytest tests/ -q`
  (green baseline = 847 passed, 6 env-skips). Never pipe pytest through `tail` in a
  `&&` chain. Commit per logical unit, `core/memory/` files only.
- **Prime Directive** — stability before new surface area: verify the layer beneath is
  correct/honest/tested before building on it; a shaky foundation is a STOP-and-propose,
  not a build-over.
- Commits go out as **clannon-bot** (shared git identity); push is the backend-agent's
  job unless coordinated. **Report** progress to `reports/memory/report_vN.md`.
