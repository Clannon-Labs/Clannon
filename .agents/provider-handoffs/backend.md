# Shared provider handoff — backend

Transfers live backend-coordinator work between Claude Code and Codex.

## Current checkpoint

- Provider: Claude Code (resumed via clannon-provider-supervisor.sh after a
  rate-limit round-trip — this exact conversation thread continued via
  `--continue`, so full context survived; only git/file state needed catching
  up on, not conversation memory)
- Updated: 2026-07-26 ~23:20
- Task: caught up on everything that happened while this session was
  rate-limited. Two things ran in parallel: the OWNER hand-debugged the crew
  failover system directly (6 commits, own git identity `thecybro`: complete
  Claude-to-Codex crew failover, recycle stale crew sessions, allow
  supervised Codex-first restart, never inject wakes into shell panes,
  recycle detached stopped supervisors, parse wrapped provider reset times —
  all in `scripts/`, all pushed as part of this batch); and `clannon-api`
  ALSO failed over to Codex and did substantial work (task-registration
  ordering fix implemented, an SSE duplicate-event race found+fixed, a
  HIGH-priority false-delivery persistence-ordering bug found+fixed, a
  fake-green test in run_cancel.py found+fixed) but couldn't commit or update
  its own tracked handoff — Codex's `--sandbox workspace-write` rejected
  `.git/index.lock` and `.agents/` writes.
- **Found + fixed a real permission bug live**: this session itself got
  resumed with `--permission-mode dontAsk`, which silently denied tmux
  control entirely (a whole tool category, not a per-call prompt) — caught
  when I tried to capture-pane a specialist and got a hard denial. Root cause
  in `clannon-provider-supervisor.sh`: it used `dontAsk` for Claude and
  `--sandbox workspace-write` for Codex, neither of which matches the crew's
  actual established posture (`--dangerously-skip-permissions` everywhere
  else, "the owner asked for it so the crew runs unattended"). Fixed both to
  `--dangerously-skip-permissions` / `--sandbox danger-full-access`
  (`f9ec955`). **This fix only applies to NEW launches — every currently-
  running tmux session (including this one) is still running under the old,
  more restrictive flags until manually restarted.**
- Reviewed clannon-api's Codex-produced diff in full before committing
  (didn't just trust the report) — 60 targeted tests independently re-run
  green. Committed as one logical unit (`74ec81e`), responded to and archived
  all 4 of its pending proposals, granted it `run_cancel.py` test ownership,
  consolidated its own provider-handoff checkpoint on its behalf (`a4a181c`).
  Also committed a separate Codex session's Integration Contract mission work
  (Phase 0 + Phase 4, `fded1ec`) and the owner's own new operator-instructions
  doc (`d0fac15`).
- 17 commits pushed this batch, HEAD `a4a181c`, remote confirmed matching.
- Next: **tell the owner to restart all 6 crew tmux sessions** so the
  permission fix actually takes effect (kill each `clannon-<side>` session,
  then `./scripts/clannon-standup.sh dual` to relaunch everything under the
  corrected flags) — I flagged this live in chat, they said they'd do it
  themselves. After restart: this exact backend session ends and a new one
  resumes via `--continue` with full history intact (same as this
  round-trip), just now with working tmux access. Also still open: the CB4
  decision-mirror gap (cancelled/crashed runs write zero decision records)
  flagged to clannon-api's handoff but not yet formally proposed/fixed by
  anyone.
- Files touched: see Git status; never assume dirty files belong to this
  provider — frontend's uncommitted changes (next.config.ts, verified-seal
  wiring, a new verification-status component) are frontend's own in-progress
  work, left untouched.
- Verification: all commits this batch suite-green (targeted) before push;
  full detail in each commit message + `docs/RESUME.md`.

## Change note

Updated after a full rate-limit round-trip surfaced a real permission-config
bug (tmux denied under `dontAsk`) that would have silently degraded every
future resume the same way. Fixed at the source (the supervisor script) so
it can't recur, but the fix needs a manual crew restart to take effect on
already-running sessions — flagging that loudly here in case a future session
picks this up before the owner has restarted the crew.

## Previous checkpoint (2026-07-26 ~21:50)

- Provider: Claude Code
- Updated: 2026-07-26 ~21:50
- Task: coordinator heartbeat loop — HEAD `7ad3d8d`, everything pushed, tree clean of
  my changes (RELEASE_v0.2.0.md shows modified by someone else, not touched by me).
- **Owner replied** (`proposals/archive/to-backend/2026-07-26_owner-reply-api-and-
  provider-infra.md`): confirmed the dual-provider infra is theirs/trusted, told me to
  inspect + approve, and overrode my DEFER on the API specialist — explicit steer
  to delegate labor to the new Codex capacity instead of doing it myself as
  coordinator. Acted on both:
  - **Reviewed + committed the provider infra** (`dee152c`) after finding + fixing one
    real defect: `CLAUDE.md` had an unrelated URL (hcb.hackclub.com/ysws-the-carnivals)
    spliced into the middle of the word "answers" — isolated to that one spot (grepped
    everything else, clean). Also scoped `.gitignore` so only `.agents/provider-
    handoffs/` is tracked, not the ephemeral `.agents/runtime/` state.
  - **Launched `clannon-api`** (4th specialist, owns `backend/api/**`), charter +
    16-file test-ownership list in `backend/api/CLAUDE.md` (`7ad3d8d`), wired "api"
    through every crew-listing script. First assignment: run-lifecycle invariant
    audit. **Found a real bug on first use**: `clannon-provider-supervisor.sh` exits
    entirely on a role's first-ever launch instead of falling back to fresh mode (its
    own `fresh_next` retry logic should catch "no conversation found to continue" but
    didn't fire) — worked around by launching plain `claude` directly; specialist is
    up and working. Flagged to owner, not yet debugged — will hit every future new
    role and every post-reboot resume.
- **This session's own build work** (before the owner-reply detour): fixed a broken-
  main gap (D11 config half-committed), shipped CB5 seal surfacing end-to-end, closed
  D6 (retired dead `backend/config/business.yaml`), placed config for orchestration's
  cross-call workspace persistence + CB2 code-symbol-tier (`EdgeLabel.CALLS`, they
  shipped both — `efbbfa6`), found+fixed 3 more D1 long-tail items, reconciled the SSE
  contract-drift benchmark (8/8), built the CB4 durable decision-memory audit mirror
  (`55b2a47` — closes that V1_GAP_ANALYSIS item).
- Next: resume the coordinator heartbeat loop; per the owner's steer, default to
  ASSIGNING queued work to specialists (including the new `clannon-api`) rather than
  building things myself when a specialist tree could reasonably own it. Consider
  investigating the provider-supervisor fresh-fallback bug when there's a lull.
- Files touched: see Git status; never assume dirty files belong to this provider.
- Verification: all backend commits this session were suite-green (targeted, per the
  established OOM-avoidance norm) before push; full list in `docs/RESUME.md`.

## Change note

Updated by Claude Code (backend/root coordinator) after the owner's reply landed
mid-heartbeat-loop and changed the plan (API specialist launched instead of deferred;
provider infra committed instead of left alone). Retaining the prior checkpoint below
since it's the last state before that reply, useful context for why the ruling changed.

## Previous checkpoint

- Provider: Claude Code
- Updated: 2026-07-26 ~17:50
- Task: coordinator heartbeat loop — HEAD `fefd7b7`, everything pushed, tree clean of
  my changes.
- State: dual-provider supervisor installed (found mid-session, not authored by me);
  no provider switch had occurred on my side.
- Open, unresolved (NOW RESOLVED, see current checkpoint): a `Status: draft` proposal
  recommending the API specialist, ruled DEFER pending owner verification; the
  provider infra pile left uncommitted pending the same.
- Verification: supervisor scripts passed Bash syntax, ShellCheck, and diff checks.

## Checkpoint before that

- Provider: not recorded
- Updated: 2026-07-26
- Task: read `.claude/contexts/HANDOFF.md`, `docs/RESUME.md`, inboxes, latest reports, Git state
- State: dual-provider supervisor installed; no provider switch has occurred
- Next: resume latest provider-native session and continue durable mission state
- Files touched: see Git status; never assume dirty files belong to this provider
- Verification: supervisor scripts passed Bash syntax, ShellCheck, and diff checks
