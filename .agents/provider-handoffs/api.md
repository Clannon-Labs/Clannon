# Shared provider handoff — api

Transfers API & Runtime specialist work between Claude Code and Codex.

## Current checkpoint

- Provider: not recorded
- Updated: 2026-07-26
- Task: read `backend/api/CLAUDE.md`'s SPECIALIST CHARTER section, `proposals/to-api/`,
  latest report, Git state. First assignment: the run-lifecycle invariant audit (see
  charter for the full required-proof-areas list).
- State: role just created — no prior session, no prior report. Backend agent placed
  the charter + test-ownership list in `backend/api/CLAUDE.md` before first launch.
- Next: start the run-lifecycle invariant audit per the charter — write concurrency-
  focused tests BEFORE changing any structure. Do not begin with broad route
  refactoring.
- Files touched: see Git status; never assume dirty files belong to this provider.
- Verification: none recorded yet (first session).

## Change note

Created by the backend agent when launching the API & Runtime specialist
(`clannon-api`), per the owner's 2026-07-26 directive to add dedicated depth on
`backend/api/**` instead of the backend agent absorbing it inline. No earlier
shared-provider checkpoint existed for this role.

## Previous checkpoint

None.
