# HANDOFF

## This run (branch: test/registration-spec-mirror-drift)

**Task (QUEUE v2, task 2):** Add an additive characterization test that the
`@tool` / `@expert` decorators in `registry/capabilities/registration.py` copy
every spec field they currently mirror from the capability class onto the
`ToolSpec` / `ExpertSpec`, so adding a spec field without wiring the decorator
(or the reverse) is caught as drift.

**What I did:** added `backend/tests/registration_drift.py` (additive only). It
pins the *observed* mirror set (ran the decorators with a monkeypatched
`register()` so nothing touches the process-wide registry, not just read the
source):

- `@tool` mirrors from the class: `name, description, domain, tags, permission,
  input_schema, output_schema, eager, timeout_s`.
- `@expert` mirrors the same minus `timeout_s`, plus `model_role`,
  `tool_grants` (read from class attribute `tools`), and `skills`.
- Derived without a class attribute: `kind`, `impl`. Lifecycle defaults left for
  `register()`: `status`, `reason`.

Three tests per kind: a sentinel test (each mirrored field flows a non-default
value through), a field-accounting test (`dataclasses.fields == mirrored ∪
derived ∪ lifecycle`), and a derived/lifecycle test.

**Reality vs intent:** no divergence. The decorator behavior matches the task
description and the decorator docstrings (incl. the `tools` -> `tool_grants`
rename). So this was a test to write, not a needs-reviewer issue.

**Drift-catcher proven (temporary source mutations, reverted):**
- dropped the `eager=` mirror line in `@tool` -> sentinel test failed as
  expected (`@tool no longer mirrors class.eager onto ToolSpec.eager`).
- added an unwired `ToolSpec.retries` field -> accounting test failed as
  expected (`Extra items in the left set: 'retries'`).
- The reverse (decorator reads an attr for a field the spec dropped) is already
  fatal at construction: `ToolSpec(stale=...)` raises `TypeError` on discovery.

**Verification:** `pytest tests/registration_drift.py
tests/orchestrator_registry.py tests/roster_experts.py` -> 18 passed; pyflakes
clean on the new file; working tree clean apart from the new test file.

**Did NOT touch:** `registration.py`, `specs.py`, any decorator/spec, or the
global registry (intercepted via monkeypatch). No other files changed.

**Residual risk:** the accounting test only forces a *conscious classification*
of a new spec field; if someone adds a field and mis-files it under
`_DERIVED`/`_LIFECYCLE` in the test, accounting still passes while the field is
unmirrored. The sentinel test only guards fields placed in `_*_MIRRORED`, so a
new field must be added there to be sentinel-checked. This is the intended
trade-off for a characterization test: it surfaces drift and demands a decision,
it does not auto-classify.

## Next (per QUEUE.md v2)

Task 3: docs-only staleness notes in `docs/suggestions/*` for symbols the
refactor deleted (`_STAGE_LABELS`, `_STAGE_STATUS`, the `api/runs.py` god-file,
`RunState`/`RunStore` location). Verify each symbol against current code before
annotating; mark, do not rewrite, the historical analysis.
