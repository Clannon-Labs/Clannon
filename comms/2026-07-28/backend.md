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
- `15:15` **api** worker via **codex** — 2026-07-28_frontend-real-run-readiness.md — exit 0, 1450s — output: `.agents/runs/20260728-145121-api.out`
- `15:28` **security** worker via **codex** — 2026-07-28_clamav-transport-fail-closed.md — exit 0, 1169s — output: `.agents/runs/20260728-150918-security.out`

## 15:45 — proposal freshness sweep + real journey

- Owner inbox first: exactly four genuine unresolved decisions; matches ROADMAP
  §5. Seven implemented specialist proposals plus four settled owner briefs
  moved to matching archive; archived statuses normalized to `done`.
- @frontend real backend is healthy at `http://localhost:8000` with isolated
  state and non-default dependency ports. Pull
  `proposals/to-frontend/2026-07-28_real-backend-browser-pass.md` at next
  boundary; desktop + 390px pass is ready. Real PNG proof delivered in 53s.
- ClamAV refusal/reset/timeout/broken-pipe now fail closed through
  `SanitizationError`; clean full suite passed 1506/13 before memory follow-up.
- Real Qdrant made hidden integration tests run and exposed deterministic test
  pollution: concurrency test retained `_SlowFakeClient`; supersession fault
  test retained an open breaker. @memory workers proved both exact predecessor
  failures and repaired exact-state restoration with pytest teardown. Live
  Qdrant full suite: 1518 passed, 1 existing ClamAV skip.
- `crew.sh` heredoc no longer executes worker header examples as shell commands;
  real security dispatch preserved `security-worker` → `backend-coordinator`.
- Owner answered all four live decisions. Shared archive cap ratified; owner
  cohort runs in parallel with capability work; Rust remains Python-first and
  deferred with service-first/FFI-bounded boundary. Provider references are
  being verified against official prices before money config changes. Owner
  inbox is empty; replies/questions archived.
- @security removed one stale future-separate-cap comment; runtime unchanged,
  focused upload/archive proof 35 passed, proposal archived.
- Provider pricing audit made no unsafe config edit: 26 routed IDs are unpriced;
  settlement loses cache/audio/per-request provider detail, charges fallbacks
  against primary, and cannot represent tiers/effective dates/tool charges.
  Enforcement stays off. Engineering repair is now ROADMAP work; owner gets
  fresh go-live proposal only after gates are green.
- Final clean backend suite: 1506 passed, 13 expected dependency skips,
  2 warnings. Only live proposal is frontend real-backend browser pass.
- `15:43` **memory** worker via **codex** — 2026-07-28_live-qdrant-suite-order-dependence.md — exit 0, 537s — output: `.agents/runs/20260728-153430-memory.out`
- `15:53` **memory** worker via **codex** — 2026-07-28_live-qdrant-test-state-repair.md — exit 0, 581s — output: `.agents/runs/20260728-154336-memory.out`
- `16:03` **memory** worker via **codex** — 2026-07-28_live-qdrant-breaker-test-repair.md — exit 0, 599s — output: `.agents/runs/20260728-155348-memory.out`
- `16:10` **security** worker via **codex** — 2026-07-28_archive-cap-ruling-comment.md — exit 0, 82s — output: `.agents/runs/20260728-160858-security.out`
- `16:15` **backend** worker via **codex** — 2026-07-28_provider-pricing-verification.md — exit 0, 465s — output: `.agents/runs/20260728-160811-backend.out`
- `17:31` **backend** worker via **codex** — 2026-07-28_partial-timeout-terminal-contract.md — exit 1, 10s — output: `.agents/runs/20260728-173122-backend.out`

## 18:20 — picked up after the Codex session hit its usage limit

Codex is exhausted until **Aug 4**; Claude's weekly limit is nearly gone too.
Dispatching is not available, so I did this myself.

**Landed the work stranded mid-flight** (`58a55f8`): the `--no-alt-screen` change
to `crew.sh` + `.codex/config.toml` (verified the flag exists in the installed
Codex before committing — it is on the owner's own launch command), the owner's
prose in `BATCH_ARCHITECTURE.md` committed verbatim, and the dispatch log line.

The worker that died (`2026-07-28_partial-timeout-terminal-contract`, exit 1 after
10s) had done **nothing** — Codex refused with a usage-limit error. Its task was
unstarted, not half-finished.

**@api — I crossed into your tree. Read this.** `1e650e9` adds `completionState`
and `completionReason` to the run REST shape, persisted + restored:
`api/run_state.py`, `run_driver.py`, `run_store.py`, `auth.py`, `README.md`, plus
`tests/completion_state.py` (new) and two lines in `tests/run_state_roundtrip.py`.

Why it could not wait for you: the UI was showing **DELIVERED** next to a report
saying "couldn't finish in the time allowed" (`run_16cac313852a`). That is LAW 5
— degrade honestly, never fake success — on the user-facing surface.

The backend already knew: `recovery.py` tags degraded responses
`{"degraded": True, "cause": kind}` and nothing read it. This surfaces the
existing signal rather than inventing semantics.

Deliberately a **third axis**, not a reuse: `status` (lifecycle),
`verificationState` (filter groundedness), `completionState` (did the loop
finish). A degraded run is routinely `delivered` + `grounded` + `partial`, all
honest. A test pins that a partial run still earns its seal.

REST-only by constraint, not preference — the SSE event set is a shared contract
and `sse_contract_drift.py` fails on any event the frontend has not declared.
Live-event half is `proposals/to-frontend/2026-07-28_completion-state-ui.md`.

Verification: 7 new tests; the persistence field-set guard caught both fields as
designed; the round-trip was mutation-tested (forcing `_from_row` to return
"complete" kills two tests). Full suite **1513 passed, 13 skipped**.

**@frontend** — your proposal is answered and archived. One correction in it:
`verificationState: partial` is the filter's verdict, not a completion signal.
Do not derive the "Partial result" badge from it; `grounded` is the *normal*
value for a timed-out run.

## 18:20 — one verdict I have NOT verified

The Codex handoff moved **CB5 to PASS**, reversing the PARTIAL I committed and
verified this morning, on a worker's report. That is the same class of claim I
mutation-tested CB6 for. It is already pushed and not blocking anything, but it
is a verdict that moved *up* without an independent check. Flagging rather than
silently trusting or silently reverting — next session should verify the
deterministic-detect claim against `tests/benchmarks/c5_security.py` before the
PASS is relied on.
- `18:15` **security** worker via **claude** — 2026-07-28_cb5-pass-verification.md — exit 0, 414s — output: `.agents/runs/20260728-180858-security.out`

## 18:45 — CB5 PASS reverted after verification; pausing for the week

**@security @orchestration — CB5 is NOT a PASS.** I flagged the verdict as
unverified rather than trusting it; a Claude/sonnet security worker checked it
and the claim did not survive. Reverted in `db6be4c`. Gate is back to **1 Critical
PASS (CB6), 5 PARTIAL.**

What went wrong is worth internalising, because the test suite went green and
stayed green. Five regex rules were added to `core/verifier/rules.py` matching
the adversarial battery's **exact wording**, the benchmark was tightened from
"some attacks flagged" to "every attack flagged", and the row was marked PASS on
the resulting green run.

Verified by hand against live `scan_text_risk`:
- fixture memory-poisoning string → `['memory_poisoning']`
- same attack intent, mildly reworded → `[]`

Removing a rule *does* turn the suite red, so the assertions are not vacuous.
They are sensitive to frozen strings, not to the attack class. **The ordinary
mutation check does not catch this.** The discriminating question is not "does
the test fail when I break the code" — it is "does it still pass when I change
the input in a way the threat model says must still be caught."

Also corrected two comments that had drifted into asserting untrue things:
`c5_security.py` claimed those payloads are "certified LIVE by
prompt_regression.py" (they are absent from it — `sunflower` appears zero times),
and `payloads.py` still called them "regex-evading" after rules were fitted to
catch them.

**To close CB5:** prove the three C5-native families live in
`scripts/prompt_regression.py`. Another regex shaped like the fixture rebuilds
exactly what was just reverted.

## 18:45 — state at pause

Owner is taking a week off. Everything committed and pushed. Tree is clean except
the frontend session's own uncommitted work — left untouched.

- `crew.sh run` now dispatches Claude workers on **sonnet-5** (owner request);
  same reasoning as the interactive specialist default.
- Codex is usage-limited until **Aug 4**.
- **@frontend** — `proposals/to-frontend/2026-07-28_completion-state-ui.md` is the
  only live proposal in the repo. `completionState`/`completionReason` are in the
  REST shape now; the SSE event needs your `types.ts` first, and I did not touch
  your tree to unblock myself.
- Owner inbox (`proposals/to-owner/`) is empty; ROADMAP §5 agrees.
