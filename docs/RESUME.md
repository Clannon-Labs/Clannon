# RESUME — picking this mission up after a stop (power / internet / restart)

This is the durable, committed runbook for restarting the multi-agent mission. It lives in git so it
survives even a total machine loss (unlike `proposals/`, `reports/`, `HANDOFF.md`, which are gitignored
— local-only, see the durability map below). Read this first after any stop.

## What survives what

| Kind of loss | What happens | What's lost |
|---|---|---|
| **Power dies / internet off** (disk intact) | The running agent processes stop; the API becomes unreachable. **Nothing is lost** — all code is on GitHub, and all local state (proposals, reports, HANDOFF, memory, agent transcripts) survives on disk. | Nothing (just live agent context; resume from transcripts). |
| **Disk / machine lost** (disk failure, ephemeral instance) | Only what's pushed to GitHub survives. | `proposals/` (all cross-agent design + ratifications), `reports/`, `HANDOFF.*`, any uncommitted WIP, `~/.claude` memory + transcripts — ALL gitignored/local. |

**The durability gap, and what closes it:** `proposals/` and `reports/` are gitignored, so a disk loss
erases the in-flight design record. Since 2026-07-27, **`comms/` is TRACKED** — the daily
cross-agent message log survives a clone, and the rule is that a `comms/` entry must be actionable on
its own (never only a pointer into gitignored `reports/`). Ratified designs still get promoted into
committed docs (`docs/architecture/**`, ADRs, this file's snapshot).

## Resume procedure

1. **Pull the code.** `git -C <repo> fetch && git checkout main && git pull` — HEAD should be the
   last pushed commit (see snapshot below). All code + committed docs are here.
2. **Start only the agents you need.** `./scripts/crew.sh start backend` (add
   `--codex` or `--claude` to pick the provider). There is deliberately no "start everything"
   command — see `docs/architecture/CREW_WORKFLOW.md` §4.2. `crew.sh status` shows
   what's up; `crew.sh attach <role>` to watch. Operator guide:
   `scripts/instruction.md`.
3. **Re-orient the coordinator (backend/root).** Read, in order:
   `LAW/README.md` (the constitution), **`docs/architecture/CREW_WORKFLOW.md`**
   (how the crew works — canonical, supersedes older coordination docs), this
   file, `docs/benchmarks/mission/README.md` (the mission map),
   `.agents/provider-handoffs/backend.md` (live checkpoint), and
   `proposals/to-owner/` (pending owner calls).
4. **Check your channels — you PULL, nothing notifies you.**
   `comms/<today>/` (short daily status from every role, tracked in git) and
   your proposal inbox (`proposals/to-backend/` + `backend/proposals/`).
   Re-check both after each unit of work.

   There is **no** auto-wake, no idle heartbeat, and no self-armed wakeup loop —
   all three were deleted in the 2026-07-27 redesign because push-based
   injection interrupted agents mid-task. **Idle is a legitimate state:** if the
   queue is genuinely empty, write your handoff and stop.

## State snapshot (keep current at each good chunk) — updated 2026-07-27

- **2026-07-27 — CREW WORKFLOW REDESIGNED FROM SCRATCH.** Owner instruction
  (`proposals/to-backend/rethinking-decisions.md`): stop bolting fixes on a weak base.
  Canonical result: **`docs/architecture/CREW_WORKFLOW.md`** — read it before acting on
  any older coordination doc; it supersedes all of them.
  - **Push-based messaging is gone.** systemd wake path units + heartbeat timers disabled,
    removed from `~/.config/systemd/user/`, and their templates deleted from the repo.
    Nothing injects into a running agent's session any more.
  - **7 scripts deleted, replaced by 1:** `scripts/crew.sh` (`start|status|attach|stop`).
    Old commands (`clannon-standup.sh`, `agent-session.sh`, `clannon-provider-*.sh`,
    `proposal-wake.sh`, `clannon-heartbeat.sh`, `proposal-status.sh`) no longer exist.
  - **New tracked channel `comms/YYYY-MM-DD/<role>.md`** — short daily status, one file
    per role (sharded so concurrent appends can't clobber). `proposals/` = rulings only,
    `reports/` = depth. See `comms/README.md`.
  - **No auto provider failover.** Provider chosen at launch (`--codex`); an agent near
    its limit writes a handoff and stops.
  - **"Never sits idle" RETIRED** — the most expensive bad instruction we followed.
  - **Challenge-the-owner mandate** added to root `CLAUDE.md` + `AGENTS.md`.
- Open, not urgent: CB4 decision-mirror gap (cancelled/crashed runs write zero decision
  records — the write only fires inside `execute()`'s main try). Flagged in
  `.agents/provider-handoffs/api.md`; unowned so far.
- Frontend has uncommitted WIP in the tree — not backend's, leave it alone.

## State snapshot (keep current at each good chunk) — 2026-07-26 (mid-session, 4th pass) — historical

- **Last pushed HEAD:** `7ad3d8d` (2026-07-26). Everything LANDED is pushed. Backend's own tree is
  clean (`RELEASE_v0.2.0.md` shows modified by someone else, not touched by backend).
- **Owner replied** (`proposals/archive/to-backend/2026-07-26_owner-reply-api-and-provider-infra.md`)
  to the prior pass's REPLY_NEEDED report — confirmed the dual-provider infra is the owner's own
  work (trusted, asked backend to inspect + approve) and **overrode the DEFER ruling on the API
  specialist**: explicit steer to delegate labor to the new Codex capacity rather than have the
  backend coordinator keep absorbing `api/**` work inline (which is exactly what happened this
  session — CB5, the SSE fix, and CB4 were all `api/**` work backend did itself).
  1. **Provider infra reviewed + committed** (`dee152c`). Found + fixed ONE real defect during
     review: `CLAUDE.md`'s OWNER REPLY CHANNEL paragraph had an unrelated URL
     (`hcb.hackclub.com/ysws-the-carnivals`) spliced into the middle of the word "answers" — grepped
     everything else for embedded URLs, isolated to that one spot. Also scoped `.gitignore` so only
     `.agents/provider-handoffs/` is tracked (not the ephemeral `.agents/runtime/` state) — the
     original edit had un-ignored all of `.agents/` wholesale.
  2. **`clannon-api` launched** (4th specialist, owns `backend/api/**`) — charter + a 16-file
     test-ownership list added to `backend/api/CLAUDE.md` (`7ad3d8d`, resolves the collision concern
     from the earlier DEFER), "api" wired through every crew-listing script. First assignment: the
     run-lifecycle invariant audit. **Found a real bug on first use**:
     `clannon-provider-supervisor.sh` exits entirely on a role's first-ever launch (no prior session
     to `--continue`) instead of falling back to fresh mode — its own retry logic should catch this
     but didn't fire. Worked around by launching plain `claude` directly; specialist is up and
     working. Not yet debugged — will recur for every future new role and every post-reboot resume.
  3. `.agents/provider-handoffs/backend.md` is now TRACKED (committed, not gitignored) — the
     durability-gap workaround from the prior pass (mirroring it here) is no longer needed for this
     one file, though `proposals/`/`reports/` still are gitignored and still need this doc.
- Specialists at this checkpoint: memory idle (genuinely, no independent work); orchestration back
  online (rate limit reset), shipped CB2 code-symbol tier (`efbbfa6`); security idle (finished,
  reported, inbox empty); frontend active; **api brand new**, working its first assignment.
- **Since the `670a217` snapshot below, this pass (3rd) fixed 3 more real gaps + shipped 2 features:**
  - **D1 long tail**: `filter_max_revisions`/`max_text_input_chars` migrated to `settings.SECURITY`
    (`ceb4bb0`); `FILTER_TIMEOUT_S`/`FILTER_MAX_TOKENS` DELETED as dead code (zero consumers, confirmed
    against an explicit golden test proving filter deliberately has no token/timeout cap). Caught
    myself mid-session directly editing `security/sanitizers/workers/*.py` (security's tree, not
    mine) — reverted before committing, proposed the repoint to security instead; they built it
    (`a0b0837`), I deleted the resulting dead constants after (`fefd7b7`).
  - **CB5 seal surfacing's SSE-contract-drift fallout closed**: my own earlier commit (`9f9d6a4`)
    had broken `tests/benchmarks/sse_contract_drift.py` (4 failures) by adding a stream event without
    updating `api/README.md` or the harness — fixed the backend-side half (`6c430c1`); frontend closed
    the rest (`5419c7b`); refreshed the pinned fixture (`3b37d41`) — now 8/8 green.
  - **Orchestration's cross-call workspace persistence** ratified + config placed
    (`max_workspace_snapshot_bytes`, `789392d`) — they shipped it (`ea0a79d`).
  - **Orchestration's CB2 code-symbol-tier design** ratified + `EdgeLabel.CALLS` placed (`3dcd1ef`) —
    they're building the rest, currently rate-limited mid-build.
  - **D6 fully closed**: `backend/config/business.yaml` (dead duplicate of the already-placed
    `tiers/limits/model-catalog.yaml`) deleted, `api/config.py` repointed to `settings.*` (`b0e6b91`).
- **Since the `3b0f0e7` snapshot below, this pass fixed a real gap + shipped one feature + one doc fix:**
  - **D11 was half-committed — fixed.** `backend/settings.py`'s `ResilienceConfig`/`RESILIENCE` and
    `config/backend/resilience.yaml` had never been committed even though memory's repoint commit
    (`6b59429`, already merged) assumed they existed — `store.py` on `main` was reading
    `settings.RESILIENCE` with no `RESILIENCE` defined. Caught before it reached a fresh clone
    (remote was still one commit behind); committed `55f1fb6`. **Lesson: verify a config placement
    actually landed before a specialist's repoint commit that assumes it lands on top of it.**
  - **CB5 seal surfacing shipped** (`9f9d6a4`) — closes the last unchecked box in
    `PHASE_3_contract_honesty.md`. `RunState.verification_state` + a `verification` SSE event,
    built off security's follow-up proposal spec. See that commit's message for full detail.
  - **Root `CLAUDE.md` doc fix** (`670a217`) — it said "FOUR interactive sessions / two specialists,"
    missing the SECURITY specialist (`clannon-security`, real since 2026-07-06, own tree
    `security/**`). Now correctly says five/three and lists `proposals/to-security/`.
  - Filed + archived 2 cross-agent proposals this pass (archive-extraction ratification accepted;
    CB5 follow-up built+closed), flagged 15 open Dependabot alerts (all npm/frontend, not touched)
    to the frontend agent, flagged the new verification-seal fields to frontend as an optional
    UI opportunity (low priority, not blocking).
- **`retry.py` enforcement anchor LANDED** (`3b0f0e7`) — the money layer's last piece. Every LLM
  call now reserves an estimated µ$ cost before it runs and reconciles the real cost after, at
  `core/llm/retry.py::run_agent` (the sole `agent.run(` choke point). Behind
  `settings.BUDGET.enforcement_enabled` (**false by default** — fully inert, no Redis touched,
  byte-identical to before). New: `core/budget/context.py` (user_id set-once ContextVar +
  exempt opt-out + lazy broker singleton), `core/budget/cost.py::estimate_call_cost_micros`
  (pre-call worst-case), `core/llm/framework.py` builds the scope per-call (model_id via
  `model_name_for_layer`, mission_id read LIVE off `deps.ctx` — never a ContextVar mirror, see
  the anchor doc's resolution #2), `api/run_driver.py` sets the user scope alongside
  `usage_scope()`. Full suite green (1397 passed, 13 env-skips), `check_invariants.py` clean
  (7 PASS, 1 pre-existing WARN). **Remaining gates before flipping the flag on** (owner):
  real per-model prices (pricing.yaml still PLACEHOLDER), prod budgets seeded, and a security
  review of the built anchor code (queued — small, self-contained diff).
- **⚠️ OPERATIONAL — READ BEFORE RUNNING TESTS:** the 24 GB box **cannot run concurrent full
  pytest suites** (~5 GB each) — doing so OOM-killed two live specialist sessions this session.
  **Norm:** targeted tests + import-smoke for isolated/additive changes; run a full suite only
  serialized (one at a time). Redis/fakeredis/lupa are now deps (`redis` runtime; `fakeredis`+`lupa`
  dev) — `uv pip install --python backend/.venv/bin/python -r backend/requirements.txt -r backend/requirements-dev.txt`.
- **Two active tracks:**
  1. **Central config/** (owner's control panel). D1–D12 all ruled; typed loader
     `backend/settings.py` is live. **Status lives in ONE place — `docs/config/CONFIG_INVENTORY.md`.
     Read it there, not here.**

     This section used to carry its own snapshot and it rotted, as duplicated status always
     does (LAW 1). It named the ORCHESTRATOR_*/EXPERT_*/TOOL_* foundation-constant removal as
     "NEXT, blocked only on repointing a few TEST refs" — that work is finished; those
     constants are gone from `foundation/vocab/constants.py` entirely (verified 2026-07-28).
     An agent trusting this file would have gone looking for work that no longer exists.

     One durable lesson worth keeping, because it is about HOW not WHAT: ⚠️ do
     constant-repointing edits ATOMICALLY and import-smoke after — a botched multi-line-import
     insert broke `import core` tree-wide once.
  2. **Batch + Redis budget** (PHASE_BATCH_REDIS, owner brief in `proposals/to-backend/`). Split: memory =
     Kuzu-graph + memory slices; orchestration = Mission Engine + batch orchestrator; backend = foundation
     seams + reviews/merges + the Redis budget core.
- **Built + pushed SINCE RESUME (2026-07-25) — a big arc:**
  - **Money-layer DATA PLANE complete + security-hardened:** spend broker `core/budget/redis_budget.py`
    (proven: no-overspend-under-concurrency, all-or-nothing, fail-closed, idempotent) + seed
    `core/budget/seed.py` (A1 single-source ceiling, SETNX-safe period/mission seeding). Two security
    reviews caught real bugs — negative-estimate inflation (`ff2d964`) + the `user_id=="mission"` key
    collision and `:`-injection (`d7e2009`) — both fixed + regression-tested.
  - **Batch architecture — first LIVE instance + tooling:** engineering batch (`dfaec88`, `spawn_batch`
    live, `has_batches=True`); patch-apply (`24b5227`, also fixed a live truncated-read/whole-file-write
    clobber bug); nav/AST tooling designed, sequenced behind the archive-entry prerequisite (tree-sitter
    approved-in-principle, dep at build-time).
  - **Knowledge web SUBSTRATE complete + proven:** memory extractor (`809ec72`), contradiction judge
    (`9afef44`), the `_traverse` exponential blowup RESOLVED via bounded in-Python BFS (`1e81903`),
    CB2/CB3/EB3 benchmark harnesses (`6b3d4f4`, honestly PARTIAL where gated on §3.3/§3.4).
  - **Archive uploads (CB2 real-repo track):** security's `uploads.py` half (`7bfaddf` — caught that
    libmagic sniffs a zip as octet-stream, would've admitted ZERO real zips; fixed with the real zip
    parser). D8 bomb-guard floors placed. Extraction half queued to orchestration.
  - **Config-depth:** D10 usage window (`b2ff6a3`), VERIFIER_* removed (`885e4bd`), archive floors.
- **In flight per specialist (handoff docs current):**
  - **Memory:** knowledge-web substrate DONE + proven (all 4 resume tasks). NOW: fix `run_all.py` graph-db
    isolation, then likely standby — §3.3 (code symbol tier) + §3.4 (media) are OTHER trees; the EB3
    Claim↔MediaSegment schema edge is DEFERRED to EB3-build-time (do NOT add it speculatively).
  - **Orchestration:** batch + patch-apply DONE. NOW BUILDING the **Mission Engine loop-wiring** (turns on
    autonomous missions): `mission_id = session_id`, 3 native tools (start/advance/end_mission), an
    `UnlimitedBudget` stub on new `Ports.budget` (the one-line swap seam for the real broker later). Nav
    §3-§5 gated on the archive track. Batch-loader-ceiling + archive-extraction also queued.
  - **Security:** all reviews + the archive-upload half DONE. Standby reviewer (mission-wiring tools +
    archive-extraction come to it next); optionally building a no-bypass invariant grep-gate meanwhile.
- **Backend's (my) own queue:** the `retry.py` enforcement anchor is **DONE** (`3b0f0e7`, see above)
  — money layer is now data-plane + enforcement-plane complete, OFF by default. **NEXT:** route the
  anchor's diff to security for the enforcement-on gate review (small, self-contained — `core/budget/
  context.py` + the `framework.py`/`retry.py` deltas); then the µ$ **rename** of `BudgetPort`/
  `TokenBudget` (coordinate — orchestration consumes `TokenBudget` in `mission.py`); the config
  long-tail (ORCHESTRATOR_*/EXPERT_*/TOOL_* removal — test-ref repoints, edit atomically; D11;
  models.yaml→config/).
- **Owner decisions pending** (`proposals/to-owner/`): (1) OOM norm — my rec is the lightweight
  norm above (no action needed); (2) **budget go-live needs real per-model prices + infra values** —
  `pricing.yaml` + infra knobs are PLACEHOLDER; the loader is fail-closed so an un-priced model blocks
  rather than leaks (safe until set).

## Known issues

- **RESOLVED (2026-07-25) — `graph_store._traverse` exponential blowup.** Memory replaced the
  variable-length Cypher `[:IMPORTS*1..N]` (which enumerated every walk on the cyclic import graph →
  2+ min at `MAX_HOPS_CEILING`) with a **bounded in-Python BFS over fixed 1-hop MATCH queries**
  (`1e81903`) — no walk-enumeration blowup, no `ALL SHORTEST`-style crash surface by construction,
  red-teamed against the zero-edge segfault shape. The previously-skipped
  `tests/memory_graph_manager.py:83` is un-skipped and runs in ~7s. No open known issues.

## Ground truth locations
Mission: `docs/benchmarks/mission/` + `docs/benchmarks/V1_GAP_ANALYSIS.md`. Architecture:
`docs/architecture/**` (batch: `BATCH_ARCHITECTURE.md`). Laws: `LAW/README.md`. Config map:
`docs/config/CONFIG_INVENTORY.md`. Owner decisions: `proposals/to-owner/`.
