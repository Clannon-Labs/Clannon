# HANDOFF

## This run (branch: test/output-filter-fail-closed)

**Task (QUEUE v2, task 5):** Add an additive characterization test
(`backend/tests/`, mirror `output_filter.py` conventions) pinning that the output
filter stage fails CLOSED: when filter adjudication raises an infra/LLM fault,
`security/filter/filter.py` wraps it into `FilterError` and returns `flow.fail`
(the run stops, the draft is NOT delivered), never `flow.next`. Assert current
behavior; do not modify the filter.

**What I did:** added `backend/tests/output_filter_fail_closed.py` (additive
only, new file). It pins the *observed* fail-closed behavior of
`security/filter/filter.py::run` (lines 122-125, the two `except` arms). I ran
the real code path with a monkeypatched `_filter` that raises, and observed the
result before writing the asserts (pin reality, not intent).

Three tests, one per fault class, plus a shared `_assert_fails_closed` helper
that pins the invariant common to all of them:
- `status is Status.ERROR` / `ok is False` / `should_stop is True` -> the chain
  never reaches `flow.next`, and `.then()` skips delivery (`should_stop` short-
  circuits the rest of the Railway chain in `foundation/transport/flow.py:506`).
- `ctx.failed is True`, `ctx.filter_blocked is False` (a fault is distinct from a
  content block), `ctx.filter_result is None` (no draft was adjudicated through).

The per-fault tests spy on `Flow.fail` (capturing the exact exception object
handed to it) to pin the wrapping behavior:
- **generic infra fault** (`RuntimeError`) -> wrapped into a `FilterError` whose
  `.cause` is the original exception; `out.error` starts with `"output filter
  failed:"` (the wrapper message at `filter.py:125`).
- **`ModelUnavailableError`** (LLM unreachable) -> handled by the first `except`
  arm (`filter.py:122`) and passed through **as-is**, NOT re-wrapped.
- **`FilterError`** from adjudication (malformed structured output) -> also
  passed through as-is, not double-wrapped.

**Reality vs intent:** one nuance worth recording. The task says the filter
"wraps it into `FilterError`". That is exactly true only for the *generic*
exception path (`except Exception`, `filter.py:124-125`). `FilterError` and
`ModelUnavailableError` are caught by the earlier arm (`filter.py:122-123`) and
passed to `flow.fail` unchanged. Both arms still fail closed (`flow.fail` ->
`Status.ERROR` -> `should_stop`), so the security property the task cares about
holds for all three; the test characterizes the *actual* wrap/passthrough split
rather than overstating that every fault is re-wrapped. This is a test to write,
not a divergence requiring a needs-reviewer issue.

**Verification:** `pytest tests/output_filter.py tests/output_filter_retry.py
tests/output_filter_fail_closed.py tests/pipeline_chain.py` -> 9 passed. New file
imports only the public `foundation` surface (`Status` is exported from
`foundation/__init__.py`), matching the foundation one-public-surface rule.

**Did NOT touch:** `security/filter/filter.py`, `schemas.py`, the locked `filter`
prompt, or any other file. Filter source is unchanged; this is purely additive
coverage.

**Residual risk:** the tests monkeypatch `_filter` (the adjudication seam) and
spy on `Flow.fail`, so they characterize the stage's *exception-to-Flow*
conversion, not the real LLM call inside `_filter`/`run_structured`. If a future
refactor moved fault handling out of `run` (e.g. into `_filter` returning a
sentinel instead of raising), these tests would need updating, by design, since
they pin the current try/except contract. The generic-fault test also depends on
the `"output filter failed:"` wrapper-message prefix; a reword of that f-string
would fail the prefix assert (intended: it pins the wrap is the generic arm).

## Next (per QUEUE.md v2)

Task 6: additive characterization test (`backend/tests/`, extend
`sanitizer_runner.py` conventions) pinning that a HIGH/CRITICAL
`pre_sanitization` result blocks in `security/sanitizers/runner.py` BEFORE any
modality worker is scheduled (assert no worker scan runs when the pre-gate
blocks). If that ordering is already asserted elsewhere, extend minimally rather
than duplicate; do not modify the runner.
