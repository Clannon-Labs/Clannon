# HANDOFF

Running notes for the unattended loop. One feature branch per task, PR to `main`.

## This run — test/foundation-all-drift

**Did:** Added an additive characterization test pinning `foundation/__init__.py`'s
`__all__` against the names its import block actually re-exports, so drift between
the two is caught. Lives in `backend/tests/foundation_contracts.py` (mirrors the
existing plain-function pytest convention there):

- `_names_bound_by_import_block()` — AST-parses `foundation/__init__.py` and
  collects every name bound by a relative `from .X import (...)` statement
  (alias-aware; `__future__` and star imports ignored).
- `test_all_mirrors_the_import_block` — asserts that set equals `set(__all__)`,
  reporting `missing` (imported but not advertised) and `stale` (advertised but no
  longer imported) separately.
- `test_all_has_no_duplicates` — no accidental dupes in `__all__`.
- `test_every_all_entry_resolves_on_the_module` — every advertised name is a real
  module attribute (`from foundation import X` works).

**State:** No current drift — import block and `__all__` match exactly (52 names),
so this is a clean PR, not a needs-reviewer issue. `backend/tests/` collects 283
tests; `foundation_contracts.py` runs 10 passed (7 prior + 3 new). Verified the new
assertion fires on injected drift.

**Mid-flight:** none.

**Next (from QUEUE.md):** the parallel-stage-array alignment regression test
(`core/pipeline.py ACTIVE_STAGES` vs `main.py _STAGE_LABELS` vs the `api/runs.py`
stage-status list).

**Risks:** none. Test-only, additive, no production code touched.
