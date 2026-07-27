# release — 2026-07-27

## Release readiness

- **NOT READY.** `main` at `535f623`; local and `origin/main` aligned after fetch.
- Latest CI run `30265956276` failed. Frontend build passed; backend job never
  ran tests because workflow installs `requirements.txt` only and `pytest`
  lives in `requirements-dev.txt`.
- Local backend verification also unavailable: `pytest` is not installed in
  current environment.
- Worktree has untracked editor-agent config files, including release-owned
  `.github/copilot-instructions.md`.
- No new tag, release draft, changelog entry, commit, or push created.
- Release process may start after CI workflow fix, green backend suite, and
  explicit release scope/version selection. Publishing still needs owner
  confirmation.

## CI repair follow-up

- Fixed CI dependency install in `275a3d7`; fixed module-path-safe pytest
  invocation in `576470c`. Both pushed.
- Local exact suite: **1488 passed, 13 skipped**.
- Fresh CI now runs full backend suite but fails 5 tests because bare
  `pydantic-ai` resolved to 2.18.0; project venv uses 2.4.0.
- Failures include usage-limit classification and paid-loop bounds. This is
  backend dependency/runtime policy, not release config.
- Filed HIGH proposal:
  `proposals/to-backend/2026-07-27_release-blocked-pydantic-ai-drift.md`.
