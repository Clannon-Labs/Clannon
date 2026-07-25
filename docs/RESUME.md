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

## State snapshot (keep current at each good chunk) — updated 2026-07-25 (mid-session)

- **Last pushed HEAD:** `6b3d4f4` (2026-07-25). Everything LANDED is pushed; specialists have live
  WIP in their own trees (memory: run_all; orchestration: mission-wiring; that's expected mid-session).
  Backend's own tree is clean.
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
     Since resume: **D10** (usage window), **VERIFIER_*** removed, **archive bomb-guard floors**
     (`settings.SECURITY.archive_*`) all DONE. **NEXT config:** the ORCHESTRATOR_*/EXPERT_*/TOOL_*
     foundation-constant removal (production repointed, blocked only on repointing a few TEST refs —
     `tests/{turn_wall_clock,model_settings,orchestrator_turn_budget,request_overload_throttles_cheap}.py`;
     ⚠️ do these edits ATOMICALLY + import-smoke — a botched multi-line-import insert broke `import core`
     tree-wide once this session); D11 `resilience.yaml` (touches memory's `store.py` — coordinate);
     `models.yaml` → `config/models.yaml` (touches orchestration's registry loader — coordinate). Full
     map: `docs/config/CONFIG_INVENTORY.md`.
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
- **Backend's (my) own queue:** the **`retry.py` enforcement anchor** — DESIGN LOCKED (full spec in
  `docs/architecture/BUDGET_ENFORCEMENT_ANCHOR.md`) and **NOW UNBLOCKED** — orchestration's mission-wiring
  landed (`01e0625`/`d29f76e`): `ctx.mission_id` is set in loop.py's `_sync_mission_state`, and
  `Ports.budget=UnlimitedBudget` is the one-line swap seam for the real broker. **THIS IS THE NEXT BUILD:**
  the anchor reads ctx.mission_id fresh per-LLM-call in `framework.py`, behind an OFF flag. Data plane (spend+seed) done; ENABLING gated on
  real prices (owner) + prod seeding. Also queued: the µ$ **rename** of `BudgetPort`/`TokenBudget`
  (coordinate — orchestration consumes `TokenBudget` in `mission.py`, so AFTER its mission-wiring lands);
  the config long-tail (ORCHESTRATOR_*/EXPERT_*/TOOL_* removal — test-ref repoints, edit atomically; D11;
  models.yaml→config/).
- **Owner decisions pending** (`reports/DECISIONS_FOR_OWNER.md`): (1) OOM norm — my rec is the lightweight
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
`docs/config/CONFIG_INVENTORY.md`. Owner decisions: `reports/DECISIONS_FOR_OWNER.md`.
