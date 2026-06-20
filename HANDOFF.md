# HANDOFF

## This run (test/pin-per-layer-model-settings)

**Done.** Extended `backend/tests/model_settings.py` with characterization tests that
pin `core/llm/registry.py` `model_settings_for_layer` and `usage_limits_for_layer` to
their current per-layer values, so a layer silently falling back to the generic defaults
is caught.

Added:
- `test_model_settings_per_layer_are_pinned` (parametrized over all 11 layers) — exact
  dict equality on the resolved `ModelSettings`. Pins which layers carry the message-history
  cache (`anthropic_cache`: orchestrator/research/code/planner/media_expert) vs the
  prefix-only layers, plus verifier's `max_tokens`/`timeout` caps.
- `test_verifier_is_the_only_layer_with_a_token_and_timeout_cap` — guards the verifier-only
  special-case from spreading or vanishing.
- `test_usage_limits_per_layer_are_pinned` (parametrized over all 11 layers) — pins
  `(request_limit, output_tokens_limit)` for the base, no-override path.
- `test_usage_limits_per_run_overrides_resize_request_limit` — pins the `max_turns` /
  `max_output_tokens` per-run override math.

Numeric caps are tied to their `foundation.constants` values, so a deliberate constant
tune flows through while a layer dropping off its branch still fails. Verified the guard
bites: dropping `code` from `_MESSAGE_CACHE_LAYERS` in-memory makes the pinning test fail.

**Scope:** test-only. No registry values changed.

**Verification:** `cd backend && .venv/bin/python -m pytest tests/model_settings.py -q`
-> 37 passed (13 prior + 24 new).

## Mid-flight
None.

## Next / ideas
- The pinned layer list is hand-maintained in the test (`EXPECTED_MODEL_SETTINGS` /
  `EXPECTED_USAGE_LIMITS`). If a new role is added to `models.yaml`, add it here too — a
  brand-new layer is NOT auto-covered by these tests.

## Risks
- Low. Pure additive test code, no production paths touched.
