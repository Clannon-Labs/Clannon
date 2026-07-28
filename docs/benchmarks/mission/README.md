# Mission: Backend Premium-Parity + V1 Capability Pass

**Multi-session mission. This directory is the durable map — read it first every
session.** The owner's full brief lives locally in
`proposals/to-backend/BACKEND_PARITY.md` (gitignored); this committed set is the
authoritative, resumable plan.

## How to pick up in any session (backend agent)

1. Read `docs/benchmarks/V1_GAP_ANALYSIS.md` — the honest per-benchmark verdicts +
   **priority order** (the north star for what to build next).
2. Read this file's status table below. A phase file in **`mission/`** is
   active/not-done; a phase file moved to **`docs/benchmarks/reached/`** is done
   (with its outcome + proving commits recorded inside).
3. Open the lowest-numbered active phase file, do the next unchecked item, keep
   its status current. When a phase's acceptance criteria are all met, move its
   file to `reached/` with the outcome filled in.
4. Rules never to break: full suite green **before every commit**; commit per
   logical unit; **backend only** (never edit `frontend/`); Discovery→propose→
   implement for any contract/security/**structural** change (all graph work is
   propose-first); security invariants unchanged (user_id scoping, sole-broker,
   sanitization re-entry, rejected drafts never persist).

## Phase status

| Phase | File | Status |
|---|---|---|
| Diagnosis | `reached/PHASE_00_diagnosis.md` | ✅ reached — `V1_GAP_ANALYSIS.md` |
| 0 — Reconciliation | `reached/PHASE_0_reconciliation.md` | ✅ reached — integration reconciliation complete |
| 1 — Reliability | `mission/PHASE_1_reliability.md` | in progress — persisted-only surfacing done; audits open |
| 2 — Latency | `mission/PHASE_2_latency.md` | not started (needs running stack) |
| 3 — Contract & honesty | `reached/PHASE_3_contract_honesty.md` | ✅ reached — earned seal + honest docs |
| 4 — Integration Contract | `reached/PHASE_4_integration_contract.md` | ✅ reached — contract + drift enforcement |
| 5 — Capability (CB work) | `mission/PHASE_5_capability.md` | in progress — CB6 passed; CB5 PASS was claimed and reverted; other gaps remain |
| 6 — Verify | `mission/PHASE_6_verify.md` | ongoing (per commit) |
| F — Foundation hardening | `mission/PHASE_F_foundation_hardening.md` | in progress |

## Structural frame & standing rules

- **Batch Architecture** (`docs/architecture/BATCH_ARCHITECTURE.md`, `[PROPOSED]`,
  owner-authored 2026-07-04) — a batch layer between the central orchestrator and
  experts; it is largely HOW the graph-blocked benchmarks (CB2/CB3) get built.
  Propose-first + stability-first; nothing built. Supersedes the *intent* of
  Phase 5's capability work; see `mission/PHASE_5_capability.md`.
- **Prime Directive (standing):** stability before new surface area — verify the
  layer beneath is stable/correct/honest before building on it; a shaky foundation
  is fixed or flagged first, never built over.

## Priority order (from the gap analysis)

CB5, CB6, CB4 audit mirror, memory persisted-only surfacing, and earned-seal
visibility are complete. Remaining benchmark work: CB3/EB3 real media
ingestion; CB1/EB1 explanation/provenance/temporal linkage; CB2 architectural
explanation; CB4 structured tradeoffs/history + ADR participant provenance.
Cross-role ordering and owner gates live in `docs/ROADMAP.md`.
