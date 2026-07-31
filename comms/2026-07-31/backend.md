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

## dispatched workers
- `16:59` **memory** worker via **claude** — 2026-07-31_upsert-write-visibility.md — exit 0, 710s — output: `.agents/runs/20260731-164808-memory.out`
- `17:21` **memory** worker via **claude** — 2026-07-31_upsert-write-visibility.md — exit 0, 1250s — output: `.agents/runs/20260731-170044-memory.out`

## owner ruling landed (proposals/to-backend/owner_final_decision_regarding_earlier_3_worries.md)

Owner greenlit: best prompt caching, much longer/detailed system prompts per their
guide, cheaper+faster models where worth it, prompt directory restructure, and
reducing guard false positives.

**Three claims I made earlier today were WRONG and are retracted.** Recording them
because the corrections change what anyone should work on:

1. **"No prompt caching in core/llm."** False. `registry.model_settings_for_layer`
   sets `anthropic_cache_instructions` + `anthropic_cache_tool_definitions` on every
   layer and `anthropic_cache` on the multi-turn ones, tested in
   `tests/llm_framework.py` and `tests/model_settings.py`. I grepped the raw
   Anthropic API spelling (`cache_control`, `ephemeral`) instead of pydantic-ai's
   parameter names.
2. **"A remember-then-ask sequence can silently lose the write."** Measured false by
   the memory worker: 0 misses / 4800 round-trips under concurrency. See
   `proposals/archive/to-memory/2026-07-31_upsert-write-visibility.md`.
3. **"A NamedTuple keeps the existing positional unpacking working."** False —
   `retry.py` unpacked 3 names from a now-5-field tuple. The suite caught it.

**Caveat on what IS proven about caching:** the tests assert the cache *settings*
are present. That proves configuration, not cache hits. Nobody has measured
effectiveness — which is exactly what the `usage.py` change now makes possible.

## landed

- `core/llm/usage.py` — prompt-cache counters (`cache_read_tokens`,
  `cache_write_tokens`) were being silently discarded by `extract_usage`. Now
  carried through. `total_tokens` (billed) stays unchanged; `total_tokens_processed`
  (volume) added. Mutation-checked: reverting turns 2 tests red.
- `core/llm/retry.py` — attribute access instead of tuple unpacking; budget pricing
  deliberately still uses full-rate input/output only.

## dispatched

- **api** — `2026-07-31_surface-cache-token-counters.md` (surface the counters so
  cache effectiveness is observable; ROADMAP §2.4 budget go-live would mis-price
  every cached run until then).
- **api** — `2026-07-31_memory-archive-cross-user-http-proof.md` (still queued).

## for the next memory session — START HERE

`core/memory/hydration.py` ranking/thresholds (relevance floor, tier trust, top-K,
token budget) is the leading suspect for BOTH the flaky
`test_memory_store_and_recall_for_user` AND the owner's "memory doesn't work much
at all". Write visibility is ruled out at scale. Also note: orchestrator AND memory
both run on `claude-haiku-4-5` per `models.yaml` ("dev: cheap by default") — model
tier may be part of the quality complaint, test before blaming prompts.
- `17:41` **orchestration** worker via **claude** — 2026-07-31_per-batch-prompt-directories.md — exit 0, 481s — output: `.agents/runs/20260731-173329-orchestration.out`
- `17:47` **api** worker via **claude** — 2026-07-31_surface-cache-token-counters.md — exit 137, 29s — output: `.agents/runs/20260731-174722-api.out`

## paused — owner at 92% weekly usage

- Killed the api worker mid-launch: headless workers spend the SAME quota. It had
  made no changes; tree was clean.
- Landed + pushed: `6d0ef5e` (memory behind the Manager), `2547696` (cache-token
  accounting + owner rulings recorded in code), `4fd07bc` (per-batch prompt dirs).
- Owner rulings in ROADMAP §2.4/2.5/2.6: prompt depth pass (memory prompts FIRST),
  memory read-side LLM (tools-only, must not read memory directly), guard false
  positives via BETTER PROMPTS ONLY — never lowering the bar.
- `models.yaml` now explains why haiku is deliberate. Do not upgrade the tier to
  make a failure go away; that destroys the signal the setting exists to produce.
- Owner thoughts NOT archived — one of three is only half-implemented; archiving
  would bury live work. Reason recorded in `proposals/archive/to-backend/`.
- Local Qdrant container stopped.

**Queued, not dispatched (quota):** both `proposals/to-api/` items.

## session 2 — pydantic-ai 2.18.0 UNPINNED (`9f28b86`)

Owner challenged my caution on upgrading. They were right; the empirical result
settled it in their favour.

**What "silently broke the money guard" actually was:** 2.18 appends a help hint to
`UsageLimitExceeded`'s message ("...see the docs on usage limits:
.../agent/#usage-limits"). `usage limits` is one of our `_RATE_LIMIT_MARKERS`. So a
hit spend/turn ceiling classified as transient `rate_limit` and got RETRIED, past
the ceiling it enforces. No API changed; a docs link moved.

**The loop cap was never broken** — `test_orchestrator_loop_is_bounded_at_cap`
passes on 2.18 untouched. What was outsourced was the IDENTITY of a permanent
failure, read from the dependency's prose.

Fix: `classify_failure` decides ours by TYPE before inspecting text. New test pins
it against a `UsageLimitExceeded` whose message is stuffed with rate-limit markers.
Mutation-checked.

Suite on 2.18.0: **1557 passed, 0 failed, 0 skipped** (live Qdrant).

**Already paid off:** `RunUsage.cache_hit_ratio` exists in 2.18 — the thing I
hand-built counters for this morning. Wiring it is the obvious next small task, and
it answers the owner's token question directly.

**Canonical:** `docs/architecture/DEPENDENCY_VERSION_STRATEGY.md`. The rule that
matters: an upgrade never breaks us with a type error — it breaks us when a
guarantee quietly stops holding while the types still match. So contract tests must
pin BEHAVIOUR, not that we passed a parameter. Configured != works.

**Note:** `.gitignore` (M) and `CAPABILITIES.md` (untracked) appeared mid-session
from outside this agent. Left untouched.
