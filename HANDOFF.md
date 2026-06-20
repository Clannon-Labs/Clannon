# HANDOFF

## This run (branch `test/runstate-roundtrip-contract`)

**Done:** Added a persistence round-trip contract test for `api/runs.py`'s
`RunState` — `backend/tests/run_state_roundtrip.py`. Purely additive, no
production code changed (`RunState`, `persist()`, `_from_row()` untouched).

What it pins:
- Every persistable `RunState` field survives `RunStore.persist()` ->
  `RunStore.get()` (i.e. `_from_row()`) byte-for-byte.
- `full_json()` (the REST shape the frontend reads) is identical before and after
  the round-trip — no UI-visible field is lost on a restart.
- A **field-set snapshot** test: every `RunState` dataclass field must be
  classified as `PERSISTED` or `RUNTIME_ONLY`. Adding a new field fails this test
  until the author wires persistence (or marks it runtime-only) — the actual
  field-loss guard.
- A sanity test that the fixture sets every persisted field to a non-default
  value (so the round-trip genuinely exercises each one), plus owner-scoping on
  read after persist.

Verified: all 5 new tests pass; ran alongside the hermetic API tests
(`run_cancel`, `sessions_usage`, `projects`) — 20 passed. Negative-checked both
guards (dropped-field and unclassified-field) actually fail when tripped.
`pyflakes` clean. invariant-check: PASS (no boundary/import/SET issues).

Runtime-only fields explicitly excluded (by design, not a bug): `events`,
`subscribers`, `task`, `cancel_requested`, `deleted`, `session_models`
(`session_models` is consumed at execute time, gone by the terminal persist).

**Mid-flight:** none.

**Next / follow-ups:** none required. If `RunState` gains a field later, the
snapshot test will flag it — classify it in `PERSISTED`/`RUNTIME_ONLY` and, if
persisted, wire both `persist()` and `_from_row()` plus a value in
`_fully_populated_run()`.

**Risks:** none. Test-only, hermetic (throwaway SQLite via `tmp_path`), no
network/Docker/model dependency.
