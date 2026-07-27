# Phase 4 — Integration Contract (live CB6)   STATUS: complete (frontend alignment proposed)

**Goal:** create + maintain `reports/INTEGRATION_CONTRACT.md` — the single shared
source of truth both agents read (reports/ is where both agents read/write; it is
the shared, both-readable location). Frontend is now idle → a proposal + wake is
allowed.

Contents required:
- [x] Per-surface reconciliation table (from Phase 0).
- [x] Exact contract per surface: endpoint(s), request/response shape, streaming
      behaviour, timing, meaning of every rendered state.
- [x] VERIFIED seal state contract (each state, sourced from real filter output).
- [x] Hydration data contract (shape + timing).
- [x] Decision-log entry schema (every kind/field the ledger animates).
- [x] CHANGELOG: what the backend changed this pass; requested frontend alignment
      (mirror as a proposals/to-frontend/ note).
- [x] NO-DRIFT RULES: no unilateral shared-contract change; changes go through this
      file + a proposal; frontend owns rendering, backend owns data + truth;
      seal/memory surfaces always reflect PERSISTED reality.

**Acceptance:** the file exists with all sections + a mirrored proposal note.
