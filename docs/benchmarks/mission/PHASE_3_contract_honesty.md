# Phase 3 — Contract Quality & Data Honesty   STATUS: not started

**Goal:** every UI-touched endpoint typed + stable; the seal earned.

- [x] **Earn the VERIFIED seal** (CB5 visibility) — DONE (backend).
      `RunState.verification_state` (mirrors `FilterResult.groundedness` verbatim:
      grounded/partial/ungrounded/not_applicable) set unconditionally at
      `api/run_driver.py` right where `block_stage` is set — on BOTH the pass and
      block path, not just block (the bug: it was read only inside the blocked
      branch before). Emitted as a `{"type":"verification","state":...}` stream
      event, persisted, in `full_json()` as `verificationState`. Tests:
      `tests/cb5_seal_surfacing.py`. NOT done: `INTEGRATION_CONTRACT.md` doesn't
      exist yet (Phase 4 deliverable, per README) — fold this contract in when it's
      written. Frontend UI/badge wiring is its own proposal, not filed yet.
- [ ] Build-state honesty sweep of docs/ touched this pass (BUILT/PARTIAL/PROPOSED
      + file:line); delete/fix stale benchmark docs.
- [ ] Security invariants unchanged — if any optimisation weakens user_id scoping /
      sole-broker / sanitization re-entry / rejected-drafts-never-persist, STOP +
      propose.

**Acceptance:** seal verdict exposed + tested; non-waking frontend note for
wiring; docs build-state-honest.
