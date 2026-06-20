# HANDOFF

## Branch: test/sanitizer-pregate-blocks-before-workers

### What I did
Added an additive characterization test pinning the sanitizer pre-gate ordering:
a HIGH or CRITICAL `pre_sanitization` result blocks in
`security/sanitizers/runner.py` **before any modality worker is scheduled**.

- File: `backend/tests/sanitizer_runner.py` (extended, runner NOT modified).
- New `_spy_all_workers` helper installs a call-recording spy on every modality
  worker's `scan` (text/image/pdf/video/audio).
- New parametrized test `test_pre_gate_block_skips_all_workers[high|critical]`:
  forces a blocking `PreSanitizationResult`, marks ALL modalities detected (so a
  worker WOULD run if the gate didn't short-circuit), and asserts:
  - flow is `blocked`,
  - `invoked == []` (no worker scan scheduled) — the core ordering guarantee,
  - the pre-gate's threat level propagated (`out.threat == level`),
  - `out.reason == BlockReason.MALICIOUS_CONTENT.value`,
  - `out.ctx.sanitization_blocked is True`.

### Why / what motivated it
- Ordering is the runner's documented contract: `runner.py:8-13` docstring and the
  early-return at `runner.py:88-98` (pre-gate `should_block`) precede the worker
  fan-out at `runner.py:103-107`.
- `security/sanitizers/CLAUDE.md` NEVER line: "Pre-sanitization (ClamAV + YARA)
  runs FIRST ... Don't run a worker ahead of the pre-gate."
- The existing tests did NOT cover this: `test_runner_blocks_on_high_worker` stubs
  the pre-gate CLEAN and exercises a WORKER block; nothing asserted the pre-gate
  path nor that workers are skipped. So this is net-new coverage, not a duplicate.

### Reality pinned before writing (METHOD)
Ran the actual code path with worker spies before asserting:
- HIGH and CRITICAL pre-gate → `status=blocked`, `workers called=[]`,
  `out.reason='malicious_content'`, `out.threat` = the gate's level.
- Teeth check: with a CLEAN pre-gate the same 5 spies all fire (`status=ok`), so
  `invoked == []` genuinely captures the short-circuit and is not vacuous.

### What I deliberately did NOT touch
- `security/sanitizers/runner.py` (task forbids modifying the runner).
- Worker-block path / `sanitization` dict shape (covered by the existing test).
- No prompt, ADR, invariant, or doc edits.

### Tests
`python -m pytest tests/sanitizer_runner.py` → 4 passed.
`tests/sanitizer_runner.py tests/pre_sanitization.py tests/text_sanitization.py`
→ 17 passed.

### Residual risk
Low. Test is hermetic (monkeypatches the pre-gate and all workers; no ClamAV/YARA
daemon, no network, no models). It pins CURRENT behavior; if the runner's ordering
is intentionally changed later, this test will (correctly) flag it.
