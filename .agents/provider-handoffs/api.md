# Shared provider handoff — api

Transfers API & Runtime specialist work between Claude Code and Codex.

## Current checkpoint

- Provider: Claude Code
- Updated: 2026-07-26
- Task: first assignment from the charter — run-lifecycle invariant audit
  (cancel/shutdown/persistence/SSE-reconnect races).
- State: read `run_state.py`, `run_store.py`, `run_driver.py`, `sse.py`, `app.py`
  (routes + lifespan) end to end, plus existing test coverage
  (`run_cancel.py`, `run_state_roundtrip.py`, `sse_terminal_order.py`,
  `sse_failure_terminal.py`, `health_lifecycle.py`) to avoid duplicating pins.
  Wrote `backend/tests/run_lifecycle_invariants.py` (new file, 6 tests, all
  green in isolation). Found + reproduced a real race: app.py's "cancel can
  never race task registration" comment is true today only because
  `LocalArtifactStore.put` (an `async def` that never actually suspends) sits
  in the await gap between `STORE.create()` and `run.task = create_task(...)`
  — swap in any genuinely-async upload store and a concurrent cancel can win,
  report "cancelled", persist it, then get silently overwritten by the
  orphaned task's "delivered". Also found `api/README.md` overstated the SSE
  reconnect contract (claimed every reconnect replays the buffered sequence;
  false once a run is evicted to SQLite) — fixed the doc wording, pinned with
  a test. Full write-up in `reports/api/report_v1.md`.
- Next: committed in four passes (`31fc7af`, `c110893`, `fd17323`, `4a7552e`).
  Full suite green after the structurally-significant ones (1481 then 1482
  passed, 13 skipped env-only, 0 failed); the final follow_up_run
  parametrization was test-only/behavior-preserving so verified targeted
  (`run_lifecycle_invariants.py` 9 passed + adjacent run/SSE/health files 26
  passed) per the box's memory-pressure norm, not a third full run.
  `reports/api/report_v1.md` finalized. Filed
  `proposals/to-backend/2026-07-26_run-task-registration-ordering.md`
  (pending) asking for a read on finding #2's fix before implementing — a
  small, API-internal structural change with a minor user-visible timing
  effect (`run.inputs` populates a beat later on `GET /runs/:id`). DO NOT
  implement that fix until a reply lands there — no heartbeat/notification in
  this session constitutes approval. Once a reply lands (or independently):
  continue the charter's remaining required-proof-areas (cross-user access
  non-disclosure — check whether `api_access_control.py` already covers
  run/artifact/audit/project/session, or if gaps remain).
- Files touched: `backend/tests/run_lifecycle_invariants.py` (new, 9 tests),
  `backend/api/README.md` (one line, `/runs/:id/stream` row),
  `backend/api/run_driver.py` (one comment, `CancelledError` handler —
  corrected, no behavior change), `reports/api/report_v1.md` (local,
  gitignored), `proposals/to-backend/2026-07-26_run-task-registration-ordering.md`
  (local, gitignored). Nothing else — never assume other dirty files in the
  shared tree belong to this session.
- Verification: full suite green after BOTH commits (1481 passed then 1482
  passed, 13 skipped env-only, 0 failed) — this is trustworthy to build on.
  An advisor pass caught two issues in the first draft before this was final:
  a garbled/wrong claim about the shutdown-vs-user comment being "already
  correct" (it wasn't — fixed in commit 2), and a tripwire test that asserted
  its own setup rather than the actual claim (strengthened with a `call_soon`
  probe, verified it now actually fails against a suspending fake store).

## Change note

Completed the charter's first assignment (audit, not refactor): wrote
concurrency-focused invariant tests before touching any structure, per the
charter's explicit instruction. No production code changed except one
doc-accuracy line in `api/README.md` — everything else is test-only or
reporting. The proposed structural fix for finding #1 is deliberately NOT
applied yet, pending the backend agent's read (small but real behavior-timing
change).

## Previous checkpoint

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
