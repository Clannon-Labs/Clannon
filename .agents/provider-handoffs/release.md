# Shared provider handoff — release

Transfers Release & GitHub specialist work between Claude Code and Codex.

## Current checkpoint

- Provider: Codex
- Updated: 2026-07-27
- Task: prepare v0.3.0 without publishing.
- State: COMPLETE. Owner published `v0.3.0` at 2026-07-27T16:40:02Z. Release
  and tag both target `a45d8ef`. GitHub release is neither draft nor prerelease.
- Verification: local backend 1489 passed / 13 service-dependent skips;
  frontend 75 tests + lint + production build passed. GitHub backend and
  frontend jobs both passed on exact release commit.
- Files: `CHANGELOG.md`, `RELEASE_v0.3.0.md`.
- Inbox: v0.3.0 backend notes input handled and archived.
- Next: none. Release queue empty.
- Release URL: `https://github.com/vraksha/Clannon/releases/tag/v0.3.0`

## Change note

Checkpoint updated after owner publication. Change reason: v0.3.0 release
finished; no remaining release work.

## Previous checkpoint

- Provider: Codex
- Updated: 2026-07-27
- Task: release-readiness audit requested by owner.
- State: NOT READY. CI infrastructure fixed, but fresh dependency resolution
  exposed pydantic-ai loop-bound failures.
- Next: backend pins supported dependency, restores green CI, then release role
  drafts v0.3.0.
