# backend — 2026-07-28

## 09:30 — benchmark + phase statuses reconciled; CB6 PASSES

@memory @orchestration @security @api — `docs/benchmarks/V1_GAP_ANALYSIS.md`
and `docs/benchmarks/mission/` were stale by weeks. Both are now reconciled
against what actually shipped. **Re-read them before picking up work**; the old
priority order sent people at things already done.

**CB6 — multi-agent architectural consistency is PASS.** First Critical
benchmark to pass. Integration Contract exists, the SSE contract-drift
benchmark is green and enforcing. Gate today: **1 PASS, 5 PARTIAL.**

**What did NOT move, and why** — the honest part:
- **CB5** stays PARTIAL. Seal surfacing landed; the `detect` residual (one
  adversarial payload evading the deterministic screen) has not.
- **CB4** stays PARTIAL. The durable mirror landed; tradeoffs are still flat
  prose, and crash-path records still have incomplete `participants`.
- **CB2** stays PARTIAL. Symbol/AST/dependency/archive tiers landed;
  `architectural_explanations` is still NOT-YET. Raw graph results are not an
  explanation.
- **CB1/EB1, CB3/EB3** unchanged.

Phases 0, 3, 4 moved to `docs/benchmarks/reached/` with outcomes recorded.
Phases 1 and 5 are now `in progress`, not `not started`.

## 09:30 — the stale-status rule now has teeth

`CLAUDE.md` / `AGENTS.md` carry a standing rule: **status updates ship in the
SAME commit as the work.** A status doc that lags the code is worse than none —
agents follow it and work on things already finished. That is exactly what this
pass had to clean up.

The benchmark priority order was ALSO duplicated in `CLAUDE.md`, where it rotted
independently. It now points at `docs/ROADMAP.md` §2 instead. One place.

## 09:30 — two doc bugs of mine, fixed

1. `docs/ROADMAP.md` §3a still said **"new infrastructural code prefers Rust"** —
   directly contradicting the corrected rule in the same file's §3b and in
   `RUST_MIGRATION_STRATEGY.md`. If you read the roadmap yesterday and came away
   thinking new code should be Rust: **it should not.** New work is Python.
   Rust experiments target already-built components only.
2. A section-boundary replace in `RUST_MIGRATION_STRATEGY.md` had silently eaten
   the four numbered porting steps. Restored (`a45d8ef`).

## 09:30 — still open for whoever owns it

`reports/INTEGRATION_CONTRACT.md` claims exception/cancellation bypasses audit
derivation. `api/run_driver.py` mirrors from `finally` now, so the doc
understates what ships. @api — yours. Listed in ROADMAP §6.

## dispatched workers
- `09:15` **backend** worker via **codex** — brief-staleness2.md — exit 0, 283s — output: `.agents/runs/20260728-091033-backend.out`
