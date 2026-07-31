# backend — 2026-07-31

## picked up the 2026-07-30 tree

Session resumed a dirty tree that nobody had committed. Reconstructed who did what
from `.agents/runs/*.out` + mtimes rather than trusting reports:

- **memory worker (codex)** — exit 0. Manager-owned curation landed: `curator.py`,
  `items.py`, `lifecycle.py`, `manager.process_turn`, provenance in `store.py`,
  `tests/memory_curator.py`.
- **orchestration worker** — dispatched twice, **both died on provider usage
  limits before doing any work** (codex exit 1 @12s, claude exit 1 @433s).
- **backend coordinator (codex)** then did the orchestrator/pipeline/foundation/api
  migration by hand, and the `to-api` archive work that was never dispatched. Cut
  off before committing.

## what I did

Reviewed, verified and committed the whole set. Highlights:

- Acceptance grep for the orchestration proposal comes back clean across
  `core/orchestrator`, `registry`, `experts`, `tools`.
- **Audited the three deleted test files** instead of trusting a green suite —
  every test in them covered a capability the change removes. The invariant that
  had to survive (filter-blocked turn cannot seed memory) is still live in
  `tests/memory_view_blocked.py`.
- Ran the suite twice: once without Qdrant, once against a live Qdrant, because
  the skipped tests were exactly the memory/isolation ones this diff rewrites.
- Fixed a mangled docstring indent in `core/pipeline.py`.

Archived three proposals with responses: `to-memory` curation, `to-orchestration`
memory removal, `to-api` real archive. `to-frontend` memory-provenance-cards stays
open — that's the frontend instance's lane and its tree already has work in it.

## dispatched

- **api** — `2026-07-31_memory-archive-cross-user-http-proof.md`. The new
  `/memory` endpoints only prove owner scoping one layer down at the Manager;
  there is no HTTP-level two-user test. Brief tells the worker to verify that
  premise first and stop if such a test already exists.

## open for the owner (discussion, not a proposal)

Three items in `drafts/owner_thoughts/active/` all say "discuss before acting", so
nothing was built for them. Findings that change the questions:

- **The memory READ path has no LLM at all.** `hydration.py` is vector search +
  trust/recency ranking + token budgeting. The owner suspects a bad retrieval LLM;
  there isn't one.
- **The memory system prompt is 39 lines.** The secure overlay upgraded the filter
  (64 → 518) and verifier (90 → 219) but left memory at 39 → 39. The moat runs on
  the thinnest prompt in the system.
- **No prompt caching anywhere in `core/llm/`.** Every call re-sends its full
  system prompt uncached — the mechanical explanation for the token usage the
  owner noticed, and the thing that decides whether long prompts are affordable.
- **`registry/config/batches.py` hardcodes one prompt for every batch**
  (`_BATCH_PROMPT_NAME = "batch_orchestrator"`). Exactly one batch exists today,
  so the owner's per-batch prompt structure is cheap now and expensive later.
