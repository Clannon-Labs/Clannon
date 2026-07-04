# Phase 3 — Contract Quality & Data Honesty   STATUS: not started

**Goal:** every UI-touched endpoint typed + stable; the seal earned.

- [ ] **Earn the VERIFIED seal** (CB5 visibility): expose the output filter's real
      groundedness/citation-integrity verdict as a typed field + states
      (verified / partial / unverified) on the Run + a stream event. FilterResult
      today discards the groundedness signal the LLM already computes
      (security/filter/filter.py::_grounding_view). Define the contract in
      INTEGRATION_CONTRACT.md; additive, no break.
- [ ] Build-state honesty sweep of docs/ touched this pass (BUILT/PARTIAL/PROPOSED
      + file:line); delete/fix stale benchmark docs.
- [ ] Security invariants unchanged — if any optimisation weakens user_id scoping /
      sole-broker / sanitization re-entry / rejected-drafts-never-persist, STOP +
      propose.

**Acceptance:** seal verdict exposed + tested; non-waking frontend note for
wiring; docs build-state-honest.
