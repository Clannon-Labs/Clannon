# Phase 0 — Contract Reconciliation   STATUS: in progress

**Goal:** for each frontend signature surface, trace the real backend data path;
produce the UI-need / API-provides / gap / resolution table (feeds Phase 4).

Done:
- [x] Frontend surfaces digested (hydration MOMENT, live LEDGER, delivered
      REPORT + seal). Key finding: the **VERIFIED seal is decorative** —
      `frontend/src/components/brand/verified-seal.tsx` reads no data; it renders
      on `reportDone` alone. Backend exposes **no verification field**
      (`FilterResult` = proceed/blocked/reason/categories only,
      `security/filter/schemas.py`).

To do:
- [ ] Decision-log/SSE entry schema table (kinds, ts, expert-spawn, tool, elapsed)
      — is each entry sufficient to animate; incremental vs bursty flush.
- [ ] Hydration contract: shape + timing GET /memory/hydration-preview returns.
- [ ] Fold the full reconciliation table into Phase 4's INTEGRATION_CONTRACT.

**Acceptance:** the per-surface reconciliation table is complete in
INTEGRATION_CONTRACT.md with a resolution per gap.
