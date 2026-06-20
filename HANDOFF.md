# HANDOFF

## What I did (this run)
- Docs-only fix in `backend/foundation/vocab/types.py`: the `BlockReason` enum
  defines `MALFORMED_INPUT = "malformed_input"` but its docstring omitted that
  member. Added the missing docstring line (placed first to match enum member
  order, aligned with the existing entries). No code/behavior change.
- Description grounded in actual usage: `core/intake/intake.py` raises
  `MALFORMED_INPUT` for empty input (size == 0) and for expected bad input
  (`InputError`: malformed, unknown type, unreadable file).
- Verified the file still parses (`ast.parse`).

## Mid-flight
- None. Change is complete and self-contained.

## What's next
- None required for this task. PR opened against `vraksha/Clannon` base `main`.

## Risks
- None. Docstring text only; no executable code touched.
