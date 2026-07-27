# Shared provider handoff — backend

Transfers live backend-coordinator work between Claude Code and Codex.

## Current checkpoint

- Provider: Claude Code (running standalone, NOT in tmux — the owner started it
  directly to do this rewrite)
- Updated: 2026-07-27
- Task: **DONE — full crew-workflow redesign**, on the owner's explicit
  instruction (`proposals/to-backend/rethinking-decisions.md`) to rebuild from
  scratch rather than bolt more fixes on. Canonical result:
  **`docs/architecture/CREW_WORKFLOW.md`** — read that first, it supersedes every
  older description of agent coordination.
- What changed:
  - **All push-based messaging deleted.** systemd wake path units + heartbeat
    timers disabled, unenabled, and their unit files removed from
    `~/.config/systemd/user/` AND `scripts/systemd/` (the standup script used to
    silently reinstall them — that install block is gone with the script).
  - **Deleted scripts:** `clannon-standup.sh`, `clannon-provider-supervisor.sh`,
    `clannon-provider-status.sh`, `agent-session.sh`, `proposal-wake.sh`,
    `clannon-heartbeat.sh`, `proposal-status.sh`. **Replaced by one:
    `scripts/crew.sh`** (`start|status|attach|stop`). No send-keys anywhere in it.
  - **New channel `comms/YYYY-MM-DD/<role>.md`** — tracked in git, one file per
    role per day (sharded so concurrent appends can't clobber). Short status.
    `proposals/` stays for rulings, `reports/` for depth. See `comms/README.md`.
  - **No automatic provider failover.** Provider is chosen at launch
    (`crew.sh start <role> --codex`). Rationale in CREW_WORKFLOW §5.4.
  - **"Never sits idle" policy RETIRED** — it was the single most expensive bad
    instruction; see CREW_WORKFLOW §0 and §2.2.
  - **Challenge-the-owner mandate added** to root `CLAUDE.md` + `AGENTS.md`.
- Next: the owner starts the crew when ready via `./scripts/crew.sh start backend`
  (see `scripts/instruction.md`). **Do NOT restart the old way** — the old
  commands no longer exist.
- Open items inherited, none urgent:
  - CB4 decision-mirror gap: cancelled/crashed runs write zero decision records
    (the write only fires inside `execute()`'s main try block). Flagged in
    `.agents/provider-handoffs/api.md`, not yet fixed or proposed by anyone.
  - Frontend has uncommitted work in the tree (`next.config.ts`,
    `verified-seal.tsx`, `hooks.ts`, plus two untracked files under
    `frontend/src/`). **Not backend's — do not touch, stash, or clean.**
- Verification: `crew.sh` syntax-checked and smoke-tested (`status`, dead-shell
  detection, `stop`) with no live agents running. Nothing else in the repo was
  touched by this pass — no backend/ or frontend/ source changes.

## Change note

Complete redesign, not an increment. The previous checkpoint's standing order —
"tell the owner to restart all 6 crew sessions so the permission fix takes
effect" — is **obsolete and must not be acted on**: the scripts it referred to
are deleted, and the permission fix it described lives on in `crew.sh`'s launch
flags. Superseded wholesale by CREW_WORKFLOW.md.

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
