# Handoff — Security & Filter specialist (`clannon-security`)

Written 2026-07-06, end of session — backend agent is pausing (weekly limits
nearly out). This file is for whenever this tree's session resumes (a day or
a month later) — read it first, before checking `proposals/to-security/`.

## Where things stand: clean stop, everything committed + pushed

No uncommitted work anywhere in scope (`backend/security/`,
`backend/prompts/filter/`, `backend/prompts.secure/filter/`). `git log
origin/main..HEAD` for these paths is empty — everything below is on `main`
and pushed, not just local. Suite for this tree green throughout (58 passed,
1 skipped — the ClamAV-daemon skip is a sandbox-environment gap, not a
regression; see below).

## What landed this session (newest first)

- **`8ae873c`** — `security/sanitizers/uploads.py`'s `_MAX_UPLOAD_BYTES`
  repointed from `foundation.constants.MAX_INPUT_SIZE_BYTES` to
  `settings.INTAKE.max_input_size_bytes` (`config/backend/intake.yaml`).
  Behavior-preserving (52428800 both sides, 50 MiB). Backend agent then
  repointed `core/intake/intake.py` and removed the foundation constant —
  single-source complete, confirmed by them.
- **`4b20461`** — CB5, "earn-the-seal filter verdict". `FilterResult`
  (`security/filter/schemas.py`) gained `groundedness` (Literal
  `grounded`/`partial`/`ungrounded`/`not_applicable`, default
  `not_applicable`) and `checks_performed: list[str]`. Dev prompt
  (`prompts/filter/system.md`) instructs the filter to populate both every
  call. `prompts.secure/filter/system.md` (gitignored, local-only) already
  carried equivalent locked wording — verified by diff, not touched.
  Regression tests in `tests/output_filter.py` /
  `tests/output_filter_grounding.py`. Confirmed in code that
  `filter.py::run()` already sets `ctx.filter_result` unconditionally before
  the proceed/block branch — the "seal set but never read on the pass path"
  gap was already closed; this slice made the verdict itself real and
  enforced, not a code fix.
- **`c4b2cf8`** — config-wire: every `security/` consumer of the old
  `foundation.constants.SANITIZER_*`/`FILTER_MAX_RETRIES` values, plus the
  local `PII_REDACTED_ENTITIES` list and the four `filter.py` grounding
  caps, repointed to `settings.SECURITY.*` (`config/backend/security.yaml`).
  Value-locked (import-smoke confirmed identical values before commit).
  Backend agent confirmed those foundation constants are now dead and will
  drop them next `constants.py` touch (not yet done as far as this session
  knows — check `foundation/vocab/constants.py` for `SANITIZER_*`/
  `FILTER_MAX_RETRIES` before assuming they're gone).

## Read-only reviews this session (no commits, findings fed to the backend agent)

- **Budget layer** (`core/budget/redis_budget.py`, not my tree). Found and
  reported ONE CRITICAL, empirically reproduced: `reserve()` didn't validate
  `estimate >= 0`, so a negative estimate flipped the atomic Lua
  check-and-decrement into a balance-inflating increment (repro'd:
  100 → 1,000,100 on one call). Two low-severity defense-in-depth notes
  (unescaped ids in colon-delimited Redis keys; a sentinel-key collision
  edge case). **Backend agent fixed and pushed all three, `ff2d964`.**
  Full detail: `reports/security/report_v2.md`,
  `proposals/archive/to-backend/2026-07-06_budget-redis-security-review.md`.
- **B1-item-3 design** (cross-batch awareness consumption in
  `spawn_batch`, orchestration's tree). Confirmed no violation of the two
  invariants audited (batch_id server-minted/never model-supplied; the
  awareness door only reachable from the central `Capabilities.open()`, not
  a batch's own scoped gateway). One real gap: `ctx.batch_id`'s docstring
  promised behavior (`"set once per spawn_batch invocation"`) the design
  didn't implement — flagged because implementing it naively (mutating the
  shared, non-cloned `ctx` object `scoped_to()` reuses) would have
  reintroduced a concurrency race under `_BATCH_MAX_CONCURRENT=2`. **Backend
  agent fixed the docstring, `af22c6b`**, and relayed the two build notes
  (mission_id trust-boundary connective note; the `asyncio.CancelledError`
  robustness gap in the failure path) to orchestration. Full detail:
  `reports/security/report_v3.md`, response appended directly to
  `proposals/archive/to-backend/2026-07-06_b1-item3-batch-awareness-consumption-design.md`.

## Open items / where to look first on resume

1. **`proposals/to-security/`** — check first. As of this write, only
   `2026-07-06_wire-settings-and-phaseB-review-standby.md` is open
   (Status: accepted, not archived — see next item). Everything else this
   session generated is archived to `proposals/archive/to-security/`.
2. **Standing standby duty: PHASE_BATCH_REDIS invariant reviewer.** No B3
   (two-tier sole-broker / no user_id-scoping bypass) or A3
   (fail-closed-on-money / Redis-down-pauses / no un-reserved-call-path)
   design had landed in `proposals/to-security/` as of this write. Also
   standing by for **orchestration's concrete-first-batch design** (the
   actual `config/backend/batches.yaml` engineering/CB2 flagship, mentioned
   as the deliberate follow-up to B1-item-3 §6) — will need a
   scoping/sole-broker review when it lands, per the backend agent's last
   note.
3. **Confirmed already done:** `foundation/vocab/constants.py` no longer
   carries `SANITIZER_TIMEOUT_TOTAL_S`/`SANITIZER_TIMEOUT_WORKER_S`/
   `SANITIZER_MAX_WORKERS`/`FILTER_MAX_RETRIES`/`MAX_INPUT_SIZE_BYTES` — the
   backend agent's single-source cleanup already landed (checked directly
   at end of session; only a migration comment pointing at
   `settings.SECURITY.filter_max_retries` remains). Nothing to chase here.
4. **Nothing half-built.** Every commit above is a complete, tested,
   behavior-preserving slice — there is no WIP to pick back up in
   `security/filter/`, `security/sanitizers/`, or `prompts/filter/`.

## Verify command (OOM-lightweight norm, this tree)

```
cd backend && .venv/bin/python -m pytest \
  tests/pre_sanitization.py tests/text_sanitization.py tests/sanitizer_runner.py \
  tests/uploads.py tests/output_filter.py tests/output_filter_retry.py \
  tests/output_filter_grounding.py -q
```

Expect 58 passed, 1 skipped (ClamAV daemon unreachable — sandbox
environment, not a regression; a real Redis/ClamAV-backed CI run would
need to confirm that path separately, not something this session had access
to).
