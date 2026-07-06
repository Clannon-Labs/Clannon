# RESUME — picking this mission up after a stop (power / internet / restart)

This is the durable, committed runbook for restarting the multi-agent mission. It lives in git so it
survives even a total machine loss (unlike `proposals/`, `reports/`, `HANDOFF.md`, which are gitignored
— local-only, see the durability map below). Read this first after any stop.

## What survives what

| Kind of loss | What happens | What's lost |
|---|---|---|
| **Power dies / internet off** (disk intact) | The 4 agent processes stop; the API becomes unreachable. **Nothing is lost** — all code is on GitHub, and all local state (proposals, reports, HANDOFF, memory, agent transcripts) survives on disk. | Nothing (just live agent context; resume from transcripts). |
| **Disk / machine lost** (disk failure, ephemeral instance) | Only what's pushed to GitHub survives. | `proposals/` (all cross-agent design + ratifications), `reports/`, `HANDOFF.*`, any uncommitted WIP, `~/.claude` memory + transcripts — ALL gitignored/local. |

**The one durability gap:** the cross-agent coordination brain (`proposals/`) is gitignored, so a disk
loss erases the in-flight design record. Mitigations: ratified designs get captured in committed docs
(`docs/architecture/**`, ADRs, this file's state snapshot); and see the owner-decision on backing up
`proposals/` in `reports/DECISIONS_FOR_OWNER.md`.

## Resume procedure

1. **Pull the code.** `git -C <repo> fetch && git checkout main && git pull` — HEAD should be the
   last pushed commit (see snapshot below). All code + committed docs are here.
2. **Relaunch the 4 agents.** `scripts/clannon-standup.sh` opens all four in tmux
   (`clannon-{backend,memory,orchestration,frontend}`) with the right models + permissions. If the
   local disk survived, each agent can `--resume` its prior transcript; from a fresh clone they start
   fresh and re-orient from the docs.
3. **Re-orient the coordinator (backend/root = me).** Read, in order: `LAW/README.md` (the
   constitution), this file, `docs/benchmarks/mission/README.md` (the mission map),
   `reports/DECISIONS_FOR_OWNER.md` (pending owner calls), and — if present — `.claude/contexts/HANDOFF.md`
   (local anchor) + the newest `reports/report_v*.md`. If `proposals/` survived, check every inbox
   (`proposals/to-backend|to-memory|to-orchestration`) for pending items.
4. **Re-establish ownership + restart the loop.** Re-assign the batch/config split (below), then the
   coordinator arms the self-paced heartbeat (a `ScheduleWakeup` ~1200s) that keeps the team from
   idling. Two systemd `--user` layers back this up and survive a reboot: `clannon-wake@*.path`
   re-fires on inbox writes (event-driven), and `clannon-heartbeat@backend.timer` fires every 20 min
   unconditionally (the **keep-alive floor** — guarantees the coordinator never sleeps permanently even
   with a quiet inbox or a broken ScheduleWakeup chain). `clannon-standup.sh` re-installs + enables the
   timer idempotently, so it self-heals on a fresh clone. Units are version-controlled in
   `scripts/systemd/`; the ping scripts are `scripts/{proposal-wake,clannon-heartbeat}.sh` (tmux
   send-keys only — never an AI process).

## State snapshot (keep current at each good chunk) — updated 2026-07-06 (wind-down)

- **Last pushed HEAD:** `88c85f9` (2026-07-06). **Tree is CLEAN, everything pushed, nothing
  half-done** — this is a clean pause point. All code + config + docs safe on GitHub.
- **⚠️ OPERATIONAL — READ BEFORE RUNNING TESTS:** the 24 GB box **cannot run concurrent full
  pytest suites** (~5 GB each) — doing so OOM-killed two live specialist sessions this session.
  **Norm:** targeted tests + import-smoke for isolated/additive changes; run a full suite only
  serialized (one at a time). Redis/fakeredis/lupa are now deps (`redis` runtime; `fakeredis`+`lupa`
  dev) — `uv pip install --python backend/.venv/bin/python -r backend/requirements.txt -r backend/requirements-dev.txt`.
- **Two active tracks:**
  1. **Central config/** (owner's control panel). D1–D12 all ruled. Typed loader `backend/settings.py`
     is live; configs placed for budget/pricing/memory/orchestrator/experts/tools/llm/verifier/security/
     **intake**. D1 foundation-constant moves largely done + single-sourced: MEMORY_*, LLM_*, SANITIZER_*/
     FILTER_MAX_RETRIES, intake RATE_LIMIT_* + MAX_INPUT_SIZE all removed from `foundation/vocab/constants.py`.
     **NEXT config:** D10 (usage-metering window `api/app.py:689 window=30` → `budget.yaml`, scoped +
     ready); VERIFIER_* removal; the ORCHESTRATOR_*/EXPERT_*/TOOL_* foundation-constant removal (production
     repointed, **still blocked on repointing several TEST refs** — see `tests/{turn_wall_clock,model_settings,
     orchestrator_turn_budget,request_overload_throttles_cheap}.py`); D11 `resilience.yaml` (touches memory's
     `store.py` — coordinate); `models.yaml` → `config/models.yaml` with pricing colocated (touches
     orchestration's registry loader — coordinate). Full map: `docs/config/CONFIG_INVENTORY.md`.
  2. **Batch + Redis budget** (PHASE_BATCH_REDIS, owner brief in `proposals/to-backend/`). Split: memory =
     Kuzu-graph + memory slices; orchestration = Mission Engine + batch orchestrator; backend = foundation
     seams + reviews/merges + the Redis budget core.
- **Built + pushed THIS session:**
  - **Money layer (Part A):** pure µ$ cost model `core/budget/cost.py`; **Redis atomic reserve/reconcile
    broker `core/budget/redis_budget.py`** (`8d34c73`) — proven (no-overspend-under-concurrency, all-or-
    nothing, fail-closed, idempotent); **security-hardened** (`ff2d964` — rejects negative estimate, `:`-in-id
    guard, sentinel fix). Config: `budget.yaml`/`pricing.yaml` (⚠️ PLACEHOLDER prices — see below).
  - **Mission Engine (Part B):** longevity-verified capstone (`88cd786`); cross-batch awareness slice shipped
    (memory); **B1-item-3** `spawn_batch` consumes `BatchAwarenessPort` (`9e0aa19` + `1b30a1e` cancellation fix).
  - **Kuzu knowledge-web substrate** (memory, `24914b5`) — Entity/Fact/Claim/MediaSegment nodes for CB2/CB3/EB3.
  - **Foundation seam:** `mission_id`/`batch_id` on `VrakshaContext` (`478f34e`) — the ONE trusted source for
    both `BudgetScope.mission_id` and cross-batch awareness (identity-set-once).
- **In flight / next per specialist (each has a handoff doc — read it):**
  - **Memory** (`core/memory/HANDOFF_batch.md`): knowledge-web substrate landed; NEXT = the memory extractor
    (write graph twins on accepted SEMANTIC/PROCEDURAL/DECISION proposals — gate on `kind ∈ {FACT,ASSUMPTION,
    DECISION}`, NOT tier) + `GraphManager` dispatch, then the CB2/CB3/EB3 benchmark proofs.
  - **Orchestration** (`core/orchestrator/HANDOFF_mission.md`): B1-item-3 built; NEXT = the concrete first
    batch (engineering/CB2) — GREEN-LIT, propose-first: `config/backend/batches.yaml` + decomposition-test
    pass + one-batch-end-to-end proof. Then Mission-Engine loop-wiring (sets `ctx.mission_id`).
  - **Security** (`backend/security/HANDOFF.md`): CB5 + config-wire + 2 reviews done; standby invariant
    reviewer — orchestration's batch design comes to it for a sole-broker/scoping review when it lands.
- **Backend's (my) own queue:** the **`retry.py` budget-enforcement anchor** (reserve-before/reconcile-after
  each LLM call) — GATED on budget **seeding + reset-behind-interface** (Stripe deferred) not yet built; the
  honest µ$ **rename** of `BudgetPort`/`TokenBudget` (fields hold µ$ but read "tokens" — coordinate with
  orchestration, it consumes `TokenBudget` in `mission.py`); the config long-tail above.
- **Owner decisions pending** (`reports/DECISIONS_FOR_OWNER.md`): (1) OOM norm — my rec is the lightweight
  norm above (no action needed); (2) **budget go-live needs real per-model prices + infra values** —
  `pricing.yaml` + infra knobs are PLACEHOLDER; the loader is fail-closed so an un-priced model blocks
  rather than leaks (safe until set).

## Ground truth locations
Mission: `docs/benchmarks/mission/` + `docs/benchmarks/V1_GAP_ANALYSIS.md`. Architecture:
`docs/architecture/**` (batch: `BATCH_ARCHITECTURE.md`). Laws: `LAW/README.md`. Config map:
`docs/config/CONFIG_INVENTORY.md`. Owner decisions: `reports/DECISIONS_FOR_OWNER.md`.
