# Shared provider handoff — release

Transfers Release & GitHub specialist work between Claude Code and Codex.

## Current checkpoint

- Provider: not started
- Updated: 2026-07-27
- Task: role just created by the backend coordinator. No work done yet.
- State: charter at `release/CLAUDE.md`; owns CHANGELOG.md, RELEASE_*.md,
  `.github/`, `release/`, and GitHub-side state (releases, issues, PRs, labels,
  milestones, Dependabot). Operates as the `clannon-bot` account.
- Next: read the charter, then `../comms/<today>/` and `../proposals/to-release/`.
  Known open item: Dependabot alert #21 (brace-expansion GHSA-mh99) is an
  accepted dev-only residual that could not be dismissed earlier because the
  token lacked `security_events`; if the scope is present now, dismiss it as
  "tolerable risk" and note it in comms.
- Files touched: none yet.
- Verification: none yet.

## Change note

Created 2026-07-27 so the owner has a specialist to talk to for releases and
GitHub work without spending the coordinator's context on it.

## Previous checkpoint

None.
