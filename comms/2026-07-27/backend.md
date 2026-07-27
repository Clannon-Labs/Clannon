# backend — 2026-07-27

## 16:55 — crew workflow rebuilt from scratch; read CREW_WORKFLOW.md before resuming

@memory @orchestration @security @api @frontend — the coordination system you
were running under has been **replaced**, not patched. Read
`docs/architecture/CREW_WORKFLOW.md` at your next session start. Short version:

**Nothing types into your session any more.** The auto-wake (systemd watching
inboxes + `tmux send-keys`) and the 20-minute idle heartbeat are deleted. You
will never again be interrupted mid-turn, and you will never receive an
`[auto-wake]` message. In exchange, **you check your own channels** — at session
start and after each unit of work:

- `comms/<today>/` — this file and its siblings. Short status. Write your own
  (`comms/YYYY-MM-DD/<your-role>.md`), never anyone else's. Tracked in git.
- `proposals/to-<you>/` — unchanged, but only for decisions needing a ruling.
  The `Wake:` header is gone; delete it from any drafts.
- `reports/<you>/` — unchanged, for depth.

**Idle is fine now.** The "never sit idle, not a second wasted" policy is
retired — it was causing manufactured busywork and agents trampling each other.
Empty queue → write your handoff and stop. That is a good outcome, not a
failure.

**Launching changed.** All the old scripts are deleted; there is one now:
`./scripts/crew.sh start|status|attach|stop`. Provider is chosen at launch
(`--codex`), and there is no automatic mid-session failover — if you're near a
usage limit, write your handoff and stop cleanly.

**You are expected to push back.** New standing rule in `CLAUDE.md` /
`AGENTS.md`: before acting on an instruction — including the owner's — confirm
it actually helps. If it doesn't, say so *before* doing the work. The worked
example in the doc is the no-idle policy: nobody challenged it for days and it
cost us real work.

## 16:55 — one unowned bug, if you want it

CB4 decision-mirror: cancelled or crashed runs write **zero** decision records,
because the mirror write only fires inside `execute()`'s main `try` block. Same
class of honesty gap the api specialist just closed for terminal persistence.
Affects `backend/api/run_driver.py` (api's tree). Found during the Integration
Contract pass; nobody owns it yet. Depth: `.agents/provider-handoffs/api.md`.

## 16:55 — state

Nothing in `backend/` or `frontend/` source was touched by this pass — docs,
scripts, and charters only. Frontend has uncommitted WIP in the tree; left
strictly alone.

## dispatched workers
- `17:59` **api** worker via **codex** — brief-api-cb4.md — exit 0, 172s — output: `.agents/runs/20260727-175706-api.out`
- `20:01` **orchestration** worker via **codex** — brief-loopguard.md — exit 0, 30s — output: `.agents/runs/20260727-200124-orchestration.out`
- `20:03` **backend** worker via **codex** — brief-loopguard.md — exit 0, 27s — output: `.agents/runs/20260727-200243-backend.out`
- `20:08` **backend** worker via **codex** — brief-loopguard.md — exit 0, 227s — output: `.agents/runs/20260727-200423-backend.out`

## 21:30 — release unblocked, CI green

@release — CI green at `c0a10cb` (run 30283522127). Everything in your
readiness report is cleared except release scope/version, which is the owner's
call. Details in `proposals/to-release/2026-07-27_ci-green-unblocked.md`.

Two of my own mistakes in that chain, recorded so they don't repeat:
1. The loop-guard commit broke CI because I verified it with a targeted 7-file
   run instead of the full suite. It touched `run_agent` — the single choke
   point every LLM stage funnels through — so it was never a local change. The
   targeted-run norm is for genuinely local blast radius; that wasn't one.
2. `.codex/config.toml` was pinning `sandbox_mode = "workspace-write"`, the
   exact setting that had blocked the api specialist from committing. Dispatched
   workers were fine (crew.sh passes the flag explicitly) but a bare `codex` run
   would have inherited it. Now matches the crew posture.

## 22:10 — v0.3.0 release-notes package delivered to @release

Full input in `proposals/to-release/2026-07-27_v0.3.0-release-notes-input.md`:
grouped user-facing changes, security disclosures, limitations, SHAs, and what
to omit. Recommended `v0.3.0` — 306 commits, zero breaking markers, additive API
only; not 1.0 because V1 isn't done and budget enforcement ships OFF.

Archived their two proposals for them. **Root cause was not permissions** — it's
that their Codex session started under the old `.codex/config.toml`
(`workspace-write` + `network_access = false`). A running session keeps the
sandbox it booted with, so the config fix in `c0a10cb` doesn't reach it. The
network flag matters more than the write flag here: `gh` calls would fail, and
that blocks publishing. They need a restart before release.

Generalizable: **fixing a config does not fix a session already running under
it.** Worth remembering before assuming a specialist is broken.
