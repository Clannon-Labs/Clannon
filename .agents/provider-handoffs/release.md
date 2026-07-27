# Shared provider handoff — release

Transfers Release & GitHub specialist work between Claude Code and Codex.

## Current checkpoint

- Provider: Codex
- Updated: 2026-07-27
- Task: release-readiness audit requested by owner.
- State: NOT READY. CI infrastructure blockers fixed and pushed:
  `275a3d7` installs `requirements-dev.txt`; `576470c` invokes
  `python -m pytest -q`. Local exact suite is green: 1488 passed, 13 skipped.
  Fresh GitHub run `30268084504` executes suite but fails 5 tests under
  newly-resolved `pydantic-ai==2.18.0`; project venv uses 2.4.0. Failures cover
  fatal usage-limit classification plus orchestrator/expert loop bounds.
- Worktree: untracked editor-agent config files remain, including owned
  `.github/copilot-instructions.md`. They predated audit and were untouched.
- Next: await backend response to
  `proposals/to-backend/2026-07-27_release-blocked-pydantic-ai-drift.md`.
  Recommended unblock: pin supported 2.4.0, then rerun CI. After green CI,
  resolve or intentionally exclude untracked release-owned file, choose next
  version, and draft changelog/release notes. Owner confirmation required
  before publication.
- Files touched: `comms/2026-07-27/release.md`, this handoff.
- GitHub changes: none.
- Verification: local backend suite 1488 passed, 13 skipped. GitHub run
  `30268084504`: frontend green; backend 1483 passed, 13 skipped, 5 failed.
  No open PRs. Latest published release remains `v0.2.0`.

## Change note

Checkpoint updated after first release-readiness audit. Release process not
started because CI is red and backend suite has no verified green.

## Previous checkpoint

- Provider: not started
- Updated: 2026-07-27
- Task: role just created by backend coordinator. No work done yet.
- State: charter at `release/CLAUDE.md`; owns release artifacts and GitHub state.
- Next: read charter and channels; inspect Dependabot alert #21 when relevant.
