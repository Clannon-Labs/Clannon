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

## State snapshot (keep current at each good chunk)

- **Last pushed HEAD:** `2cf4c4f` (2026-07-05). All code + config data + docs safe on GitHub.
- **Two active tracks:**
  1. **Central config/** (owner's control panel). D1–D6 approved. Phase-3 root structure committed
     (`config/README.md`, `config/backend/{tiers,limits,model-catalog}.yaml` — inert). NEXT: the typed
     loader `backend/settings.py` + rewire `api/config.py` + delete `backend/config/`, then externalize
     one area per commit (incl. the D1 `foundation/` product-knob move + `SPEND_CEILING_FRACTION=0.80`).
     Map: `docs/config/CONFIG_INVENTORY.md`.
  2. **Batch + Redis budget** (owner greenlit, propose-first, robust-not-fast). Split: memory = Kuzu-graph
     + cross-batch memory slice; orchestration = Mission Engine + batch orchestrator + budget-wiring;
     backend = foundation seams + reviews/merges + the Redis budget core.
- **Built + pushed:** Mission Engine ungated core (`876943f` — state machine, completion gate, budget
  pre-check); graph labels MISSION/TASK + BLOCKS/FEEDS/SUPERSEDES (`b0e206f`). Earlier: CB1/EB1/CB4/EB2/
  CB5/CB2, the graph substrate, BudgetPort + GraphPort contracts.
- **Ratified (design), building next:** orchestration's Mission Engine v2 (mission/task/edge on GraphPort
  labels; write-once anchor; gated evidence completion); memory's cross-batch slice as a SEPARATE
  `BatchAwarenessPort`. Open coordination: memory implements `GraphManager.members()` + generic
  property-marshalling → then backend adds `members()` to the GraphPort Protocol; Mission Engine
  completion signal → memory's `batch_store.clear_mission`.
- **Backend's own queue:** place `BatchAwarenessPort` contract; finish config Phase-3; design the Redis
  budget core (cost model → owner decision).

## Ground truth locations
Mission: `docs/benchmarks/mission/` + `docs/benchmarks/V1_GAP_ANALYSIS.md`. Architecture:
`docs/architecture/**` (batch: `BATCH_ARCHITECTURE.md`). Laws: `LAW/README.md`. Config map:
`docs/config/CONFIG_INVENTORY.md`. Owner decisions: `reports/DECISIONS_FOR_OWNER.md`.
