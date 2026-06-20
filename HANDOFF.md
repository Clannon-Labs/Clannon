# HANDOFF

## Branch: test/characterize-failure-classifiers

### What I did
Added two independent characterization test files that pin how the codebase's two
failure classifiers treat a representative table of provider exceptions, exactly
as they behave today:

- `backend/tests/llm_retry_classification.py` — pins how the retry wrapper
  (`core/llm/retry.py`, via `is_transient`) classifies each exception as
  transient-vs-fatal, observed through `run_agent`: a transient exception is
  retried (re-run reaches the success), a fatal one is re-raised on the first
  attempt. 20 parametrized rows.
- `backend/tests/orchestrator_recovery_classification.py` — pins how the
  orchestrator's graceful-degradation path
  (`core/orchestrator/utils/recovery.classify_failure`) maps each exception to
  the user-facing `rate_limit` / `timeout` / `error`. 14 parametrized rows.

The two are deliberately kept separate (the task said do not unify the
classifiers). Each file pins its own module's current behavior through its own
public surface; neither asserts the two agree. The tables make the real
divergence explicit and pinned: transient 5xx / transport faults are RETRIED by
the retry wrapper but surface to the user as a generic `error` from recovery;
the usage/quota cap is fatal to the retry budget and an `error` to the user.

All expected values were derived empirically from the running code before the
tests were written (true characterization, not aspiration).

### State
- `cd backend && .venv/bin/python -m pytest tests/llm_retry_classification.py tests/orchestrator_recovery_classification.py tests/llm_retry.py tests/orchestrator_recovery.py -q` → 53 passed.
- Full collection clean: `pytest tests/ --collect-only -q` → 314 tests collected, no errors.
- invariant-check: PASS. Both files live under `backend/tests/`, which the
  pydantic_ai-confinement invariant (§III.12) explicitly excludes; the existing
  `tests/llm_retry.py` already imports `pydantic_ai.exceptions` by the same
  precedent. No production module touched.

### Mid-flight / next
- Nothing mid-flight. Self-contained test-only change.
- Natural follow-up (NOT done here, out of this task's scope): if the classifiers
  are ever unified or `core/llm/failures.py` changes, these tables are the safety
  net that will flag any behavior shift.

### Risks
- None to runtime: no production code changed; only new test files added.
- The tables encode current behavior including the retry-vs-recovery divergence.
  If that divergence is later intentionally removed, these tests will fail by
  design and should be updated to the new behavior.
