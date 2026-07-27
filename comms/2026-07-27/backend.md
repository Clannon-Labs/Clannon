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
