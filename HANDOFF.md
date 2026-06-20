# HANDOFF

## This run (branch: test/registry-network-rescan-invariant-a)

**Done.** Added a regression test for security invariant A in the registry
capability handler (`backend/registry/capabilities/handler/tools.py`): NETWORK
tool output is re-sanitized (`scan_text`) before it can reach reasoning.

Two tests added to `backend/tests/orchestrator_tools.py` (handler is unchanged):

- `test_network_output_triggers_rescan` — spies on `scan_text` and asserts a
  `PermissionLevel.NETWORK` tool's raw string output actually re-enters the
  sanitizer, and that a passing scan's `sanitized_text` replaces the original.
- `test_non_network_output_skips_rescan` — asserts a `READ` tool's output never
  enters `scan_text`, proving the gate is keyed on `PermissionLevel.NETWORK`.

Together they bracket the `spec.permission == PermissionLevel.NETWORK` guard on
both sides: drop the guard (always sanitize) and the second test fails; never
fire it (never sanitize) and the first fails. This complements the existing
`test_network_output_sanitized`, which only covered the redaction-on-failure
branch (`passed=False`).

Verified: `pytest tests/orchestrator_tools.py -q` → 15 passed; `pyflakes` clean.

## Mid-flight

Nothing. Scoped, test-only change.

## Next

Nothing required for this task.

## Risks

None. No production code changed; the test asserts existing behavior only.
