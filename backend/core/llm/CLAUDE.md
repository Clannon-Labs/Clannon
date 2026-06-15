# core/llm/ — the single seam to the LLM framework (PydanticAI)

Owns model construction + run + provider-error translation for every LLM stage
(verifier, filter, orchestrator, experts). `framework.py` is the single door:
`build_agent` / `build_tool_agent` + `run_structured`.

## NEVER
- This is the ONLY module in the repo that may import `pydantic_ai` (invariant
  §III.12). No other module imports the SDK — if you find one, the boundary leaked.
- All SDK types are confined here: `BinaryContent` (media), `RunContext`,
  `ModelMessage` history conversion, `UsageLimits`. Callers pass neutral types
  (an output schema, a prompt name, `(bytes, mime)` media tuples, `{role, content}`
  history dicts) and get back validated structured output — NEVER an SDK object.
- This does NOT own `Flow`, prompt content, schemas, or orchestration logic.
  Model build/run/error-translation only.

## Conventions
- Model + settings + usage limits resolve per layer from `models.yaml` via
  `core/llm/registry.py` (capability-first, provider-second — invariant §VI.23).
- Framework/provider failures translate to foundation errors: a usage/turn-cap
  breach → `MaxRetriesExceededError` (fail closed at the cap); any other failure
  → `ModelUnavailableError`. Transient 429/5xx/timeout retry with backoff lives in
  `retry.py` (`run_agent`); foundation errors propagate unchanged.
- `build_agent` is cached (long-lived structured agents); `build_tool_agent` is
  per-run (tools + deps are per-run, not cached).

## Tests
`tests/llm_framework.py`, `tests/llm_retry.py`, `tests/model_settings.py`, `tests/llm_keys.py`.

## Authoritative docs
`core/README.md` → LLM layer; `docs/architecture/SYSTEM_ARCHITECTURE.md` → LLM Framework Layer.
