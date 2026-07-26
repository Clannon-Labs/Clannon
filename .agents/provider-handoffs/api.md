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
- Next: full suite run kicked off (backgrounded, this box serializes it — see
  `docs/RESUME.md`). Once green, commit `backend/api/README.md` +
  `backend/tests/run_lifecycle_invariants.py` scoped explicitly. Then: (a)
  await backend agent's read on the proposed fix for finding #1 (reordering
  task registration in app.py + moving persist_inputs inside execute()) before
  implementing — flagged in the report because it has a small user-visible
  timing effect (`run.inputs` populates a beat later); (b) continue the
  charter's remaining required-proof-areas (cross-user access non-disclosure —
  check whether `api_access_control.py` already covers run/artifact/audit/
  project/session, or if gaps remain).
- Files touched: `backend/tests/run_lifecycle_invariants.py` (new),
  `backend/api/README.md` (one line, `/runs/:id/stream` row),
  `reports/api/report_v1.md` (new). Nothing else — never assume other dirty
  files in the shared tree belong to this session.
- Verification: `run_lifecycle_invariants.py`'s 6 tests pass in isolation
  (1.97s). Full-suite pass pending at time of this checkpoint write — confirm
  before trusting this as "safe to build on" in a follow-up session.

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
