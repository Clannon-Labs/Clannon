# Phase 3 — Contract Quality & Data Honesty   ✅ REACHED 2026-07-28

**Goal:** every UI-touched endpoint typed + stable; the seal earned.

- [x] **Earn the VERIFIED seal** (CB5 visibility) — DONE (backend).
      `RunState.verification_state` (mirrors `FilterResult.groundedness` verbatim:
      grounded/partial/ungrounded/not_applicable) set unconditionally at
      `api/run_driver.py` right where `block_stage` is set — on BOTH the pass and
      block path, not just block (the bug: it was read only inside the blocked
      branch before). Emitted as a `{"type":"verification","state":...}` stream
      event, persisted, in `full_json()` as `verificationState`. Tests:
      `tests/cb5_seal_surfacing.py`. Contract is recorded in
      `reports/INTEGRATION_CONTRACT.md`. Frontend UI/badge wiring was recorded
      through a pull-based
      proposal; no session wake/injection is used.
- [x] Build-state honesty sweep of docs/ touched this pass (BUILT/PARTIAL/PROPOSED
      + file:line); delete/fix stale benchmark docs.
- [x] Security invariants unchanged — no optimisation weakened user_id scoping,
      sole-broker, sanitization re-entry, or rejected-drafts-never-persist.

**Acceptance:** seal verdict exposed + tested; non-waking frontend note for
wiring; docs build-state-honest.

**Outcome:** reached. Real filter groundedness is streamed and persisted,
covered by `tests/cb5_seal_surfacing.py`; frontend alignment was documented via
proposal; benchmark/mission docs were reconciled without changing security
invariants. CB5 remains PARTIAL solely because detect retains a residual.
