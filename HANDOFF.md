# HANDOFF — Clannon unattended loop

This file is the running memory for the unattended self-improvement loop. Each
loop iteration reads THIS file and `CLAUDE.md` FIRST, performs exactly one
`QUEUE.md` task on a fresh feature branch, opens a PR to `main`, and updates this
file on that branch.

## What this loop is
A headless Claude Code agent improving Clannon while the maintainer is away
(~40 days from 2026-06-20). It NEVER merges and NEVER touches `main` — it only
opens PRs for later human review. Branch protection on `main` enforces this
server-side (required review, no self-merge, no force-push).

## Absolute rules (do not break)
- Cut a NEW feature branch from `main`. Never commit, push, or merge to `main`.
  Never force-push. No destructive git.
- Obey `CLAUDE.md`'s scope fence and the 27 invariants in
  `docs/vision/INVARIANTS.md`. Locked security-boundary prompts (verifier,
  filter) are off-limits. Proposed ADRs 0005 / 0008 / 0009 and rejected ADR 0006
  are OUT OF SCOPE.
- One `QUEUE.md` task per run. Allowed scope ONLY: additive tests,
  characterization/regression coverage of EXISTING behavior, and pure
  documentation fixes. No security fixes/patches, no prompt edits, no refactors,
  no new experts/tools.
- If a task is ambiguous, needs maintainer judgment, is out of scope, or a test
  reveals a REAL gap: DO NOT guess and DO NOT change code to "make it pass."
  Open a GitHub issue labeled `needs-reviewer` with a one-line reason and stop
  without opening a code PR.
- Inspect existing code before changing it. Keep edits tightly scoped. Run
  targeted tests before opening the PR.

## How to work the codebase
- Backend tests live in `backend/tests/<topic>.py`; pytest is configured in
  `backend/pyproject.toml`; dev deps in `backend/requirements-dev.txt`. Mirror
  the existing test conventions (e.g. `model_settings.py`, `llm_retry.py`,
  `orchestrator_recovery.py`, `foundation_contracts.py`).
- The frontend has NO test runner and is owned by its own `frontend/AGENTS.md`.
  Do not add frontend tests or touch frontend code from this loop.
- Read `docs/00_START_HERE.md` for documentation precedence before relying on any
  doc.

## Status log
- 2026-06-20: Loop seeded. No tasks attempted yet. `QUEUE.md` holds 12 tasks
  (additive tests + doc fixes). Ledger is empty.
- 2026-06-20: Doc fix on branch `docs/errors-fix-constant-refs`. In
  `backend/foundation/vocab/errors.py`, two error docstrings named constants
  that do not exist in `foundation/vocab/constants.py`. Corrected to the real
  ones, docstring text only, zero behavior change:
  - `InputTooLargeError` (L84): `MAX_INPUT_TOKENS` → `MAX_TEXT_INPUT_CHARS`
    (the actual text-content char cap; `MAX_INPUT_SIZE_BYTES` left as-is).
  - `MaxRetriesExceededError` (L239): `MAX_FILTER_RETRIES` → `FILTER_MAX_RETRIES`
    and `MAX_TOOL_RETRIES` → `TOOL_MAX_RETRIES` (word-order was inverted; both
    real constants).
  Verified all three replacements exist in `constants.py` and the module still
  parses (`ast.parse`).

## In flight / next
- Nothing in flight. PR opened for the doc fix above. Next = the first unchecked
  `- [ ] ` line in `QUEUE.md`.

## Risks / open notes
- Each iteration branches fresh from `main`, so this HANDOFF does not accumulate
  across iterations (cross-run progress is tracked by the loop's local ledger,
  not by this file). Treat the Status log above as per-PR context.
