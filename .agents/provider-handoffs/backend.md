# Shared provider handoff — backend

Transfers live backend-coordinator work between Claude Code and Codex.

## Current checkpoint

- Provider: Claude Code
- Updated: 2026-07-26 ~17:50
- Task: coordinator heartbeat loop — HEAD `fefd7b7`, everything pushed, tree clean of
  my changes. This session: fixed a broken-main gap (D11 config half-committed),
  shipped CB5 seal surfacing end-to-end, closed D6 (retired dead
  `backend/config/business.yaml`), placed config for orchestration's cross-call
  workspace persistence + CB2 code-symbol-tier (`EdgeLabel.CALLS`), found+fixed 3 more
  D1 long-tail items (filter_max_revisions, max_text_input_chars, 2 dead FILTER_*
  constants deleted, 4 sanitizer caps repointed by security then cleaned up by me),
  reconciled the SSE contract-drift benchmark (now 8/8).
- State: dual-provider supervisor installed (found mid-session, not authored by me —
  see flag below); no provider switch has occurred on my side.
- **Open, unresolved:** a `Status: draft` proposal (`From: workspace-audit`, not a
  known agent) recommends launching a 4th specialist (`clannon-api`, on Codex) and
  claims unverified owner pre-approval. Per advisor consult + the document's own §8
  deferral criterion (no queued API backlog right now): ruling is DEFER, routed to
  the owner via `reports/REPLY_NEEDED_api-specialist-and-provider-infra.md`. **Do NOT
  launch `clannon-api` or run `clannon-standup.sh dual` without a verified owner
  instruction landing in `backend/proposals/` or a committed doc.**
- **Uncommitted infra flagged, not mine to commit blind:** root `CLAUDE.md`
  (`@AGENTS.md` include), root `AGENTS.md`, ~15 module `AGENTS.md` files,
  `scripts/agent-session.sh`/`clannon-heartbeat.sh`/`clannon-standup.sh` changes, new
  `scripts/clannon-provider-{status,supervisor}.sh` — appeared mid-session, coherent-
  looking but I didn't author it. Do not `git add -A` this pile.
- Next: resume the coordinator heartbeat loop; await the owner's REPLY_NEEDED
  response before touching the API-specialist question or committing the provider
  infra pile. Orchestration is hard-rate-limited until ~20:25 (Asia/Kathmandu) — don't
  nudge it, that's expected, not idleness.
- Files touched: see Git status; never assume dirty files belong to this provider —
  `backend/registry/capabilities/handler/code_symbols.py` is orchestration's in-flight
  CB2 work (untracked, mid-build when they hit the session limit), not backend's.
- Verification: all backend commits this session were suite-green (targeted, per the
  established OOM-avoidance norm) before push; full list in `docs/RESUME.md`.

## Change note

Updated by Claude Code (backend/root coordinator) mid-heartbeat-loop, prompted by the
heartbeat wakeup's new instruction to maintain this file before compaction/context
exhaustion. Retaining the original dual-provider-supervisor-install checkpoint below
since it documents infra state I didn't create and haven't fully verified.

## Previous checkpoint

- Provider: not recorded
- Updated: 2026-07-26
- Task: read `.claude/contexts/HANDOFF.md`, `docs/RESUME.md`, inboxes, latest reports, Git state
- State: dual-provider supervisor installed; no provider switch has occurred
- Next: resume latest provider-native session and continue durable mission state
- Files touched: see Git status; never assume dirty files belong to this provider
- Verification: supervisor scripts passed Bash syntax, ShellCheck, and diff checks
