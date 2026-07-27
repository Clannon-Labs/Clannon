# Phase 0 — Contract Reconciliation   STATUS: complete

**Goal:** for each frontend signature surface, trace the real backend data path;
produce the UI-need / API-provides / gap / resolution table (feeds Phase 4).

Done:
- [x] Frontend surfaces digested (hydration MOMENT, live LEDGER, delivered
      REPORT + seal). Updated finding: backend now surfaces the real output-filter
      verdict end to end (`FilterResult.groundedness` →
      `RunState.verification_state` → `verification` SSE event + persisted REST
      `verificationState`, commits `9f9d6a4`/`6c430c1`/`3b37d41`). Frontend types
      the field/event but still renders `VerifiedSeal` on `reportDone` alone and
      discards the live verification event; frontend alignment remains open.

To do:
- [x] Decision-log/SSE entry schema table (kinds, ts, expert-spawn, tool, elapsed)
      — is each entry sufficient to animate; incremental vs bursty flush.
- [x] Hydration contract: shape + timing GET /memory/hydration-preview returns.
- [x] Fold the full reconciliation table into Phase 4's INTEGRATION_CONTRACT.

**Acceptance:** the per-surface reconciliation table is complete in
INTEGRATION_CONTRACT.md with a resolution per gap.
