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

## 10:15 — follow-up: I shipped the bug I was fixing

@memory — read this one. My first reconciliation commit left `docs/ROADMAP.md`
§2 and §4 saying **CB1 "needs `valid_at` typing"** while the gap analysis in the
same commit recorded that typing as landed. If you had picked up the roadmap
this morning you would have built something that already exists. Fixed in
`00737ee`. Your real remaining CB1 work: **retrieval explanation, complete
provenance, explicit supersession linkage.**

Two more from the same pass:
- `reports/INTEGRATION_CONTRACT.md` was **gitignored** — CB6's PASS rests on it
  existing and it was absent from a fresh clone. Now tracked. (The pattern had
  to become `reports/*`; git does not descend into an excluded directory, so the
  `!` re-include was dead.) Everything else in `reports/` stays ignored.
- PHASE_6 told us to write per-benchmark status into
  `CLANNON_V1_ATTENTION_THRESHOLD.md`. That is the owner's spec of the bar, not
  a status surface — doing it would have created a **fourth** place for verdicts
  to rot. Now points at `V1_GAP_ANALYSIS.md`. One verdict, one place.

CB6's PASS was re-verified directly, not taken from the worker's summary:
8 tests, zero skips, and a deliberately mutated fixture is caught. Frontend tree
is clean, so the green reproduces from committed state.

## dispatched workers
- `09:15` **backend** worker via **codex** — brief-staleness2.md — exit 0, 283s — output: `.agents/runs/20260728-091033-backend.out`
- `09:41` **api** worker via **codex** — brief-contract-audit.md — exit 0, 91s — output: `.agents/runs/20260728-094010-api.out`
- `11:32` **security** worker via **codex** — 2026-07-28_cb5-detect-residual.md — exit 0, 97s — output: `.agents/runs/20260728-113024-security.out`
- `11:32` **orchestration** worker via **codex** — 2026-07-28_workspace-concurrency-race.md — exit 0, 144s — output: `.agents/runs/20260728-113024-orchestration.out`
- `11:35` **api** worker via **codex** — 2026-07-28_terminal-participants-auth-sweep.md — exit 0, 283s — output: `.agents/runs/20260728-113024-api.out`
- `11:36` **backend** worker via **codex** — 2026-07-28_cb5-deterministic-verifier.md — exit 0, 222s — output: `.agents/runs/20260728-113242-backend.out`
- `11:39` **orchestration** worker via **codex** — 2026-07-28_workspace-race-repair.md — exit 0, 366s — output: `.agents/runs/20260728-113324-orchestration.out`
- `11:44` **orchestration** worker via **codex** — 2026-07-28_workspace-transaction-proof.md — exit 0, 129s — output: `.agents/runs/20260728-114203-orchestration.out`
- `11:51` **orchestration** worker via **codex** — 2026-07-28_workspace-lock-extraction.md — exit 0, 87s — output: `.agents/runs/20260728-115027-orchestration.out`
- `11:53` **api** worker via **codex** — 2026-07-28_run-driver-size.md — exit 0, 157s — output: `.agents/runs/20260728-115027-api.out`
- `12:03` **backend** worker via **codex** — 2026-07-28_config-inventory-reconcile.md — exit 0, 243s — output: `.agents/runs/20260728-115919-backend.out`

## 12:30 — owner decisions moved out of reports

Owner reply channel is now `proposals/to-owner/`, one standard proposal per
decision. `reports/` is information-only. Four live gates migrated; all previous
owner-decision archives moved to `proposals/archive/to-owner/`. ROADMAP §5 and
owner inbox must stay synchronized.
