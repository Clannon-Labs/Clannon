# foundation/ — shared vocabulary + Flow transport (the base layer)

Owns the primitives every other layer imports: `Flow` (the only inter-stage
transport), `VrakshaContext`, shared enums/errors/constants, and cross-stage
contracts (`NormalizedInput`, `OrchestratorResponse`, the `MemoryPort` boundary).

## NEVER
- `foundation` imports NOTHING else in the repo. Deps point *here*; the reverse
  is a bug. (This is why model/prompt/capability loading lives in `registry.config`,
  not here — foundation can't depend on registry.)
- No LLM calls, no provider SDK, no business / sanitizer / memory-retrieval logic.
  Values, types, and transport only.
- Single-stage types do NOT live here. `VerificationResult` → `core/verifier/schemas.py`;
  `FilterResult` → `security/filter/schemas.py`. Only genuinely cross-stage shapes belong here.
- `__init__.py` is the only public surface: `from foundation import X`, never
  `from foundation.transport.flow import X`. Constants via the module:
  `from foundation import constants` then `constants.VERIFIER_TIMEOUT_S`.

## Conventions
- Every stage takes a `Flow` and returns a `Flow` via `Flow.load/next/block/warn/fail`.
  Nothing else crosses a stage boundary; exceptions are converted to Flow
  transitions at the edge (`flow.block` for threats, `flow.fail` for infra/code faults).
- Errors are organized by layer (1xx input / 2xx security / 3xx orchestrator /
  4xx infrastructure). Raise specific errors carrying `trace_id`, never bare `Exception`.
- `coerce_to_bytes` is the single "a str is text, never a path" boundary — use it.
- Log with `flow.summary()` / `ctx.snapshot()`, never the raw flow/ctx object.

## Tests
`tests/foundation_contracts.py`, `tests/pipeline_chain.py` — `python -m pytest tests/` from `backend/`.

## Authoritative docs (don't restate here)
`foundation/README.md`, `foundation/FLOW_GUIDE.md`,
`docs/architecture/ARCHITECTURAL_CONVENTIONS.md`, ADR `docs/decisions/accepted/0001-flow-only-transport.md`.
