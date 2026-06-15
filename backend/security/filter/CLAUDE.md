# security/filter/ — the output filter, sole output gate

Owns the final content gate before delivery: a small fast structured-output LLM
that checks the orchestrator's draft for safety/policy and groundedness.

## NEVER
- Filter output is structured-only (`FilterResult`). It runs on the FINAL response
  only — NEVER on the decision-log stream (that's delivered directly to the user).
- On block it STOPS the chain (delivery is skipped) so unsafe content never reaches
  the user. At the checkpoint there is no re-orchestration retry loop. Infra/model
  faults `flow.fail` (fail closed).
- Don't weaken the prompt. `filter` is a `locked` security-boundary prompt: real
  text in `prompts.secure/filter/system.md`, committed `prompts/filter/system.md`
  is the dev/CI baseline; prod fails closed if it rides the baseline.
- The filter MUST see the actual grounding content to judge groundedness: expert
  findings' `full_content`, the orchestrator's own SUCCESSFUL tool results, and
  hydrated memory are all legitimate grounding. A count + URL list is not enough.
  `did_research=False` ⇒ a direct/conversational answer that groundedness does not
  apply to. (This is the regression that once blocked benign reports — the filter
  was never shown the findings. Don't reintroduce it.)

## Conventions
- Checks: policy/safety, hallucination markers, citation integrity, PII, schema
  conformance. Bounds on the grounding payload (`_MAX_FINDINGS`, `_FINDING_CHARS`,
  tool-result caps) keep the call cheap. Runs the same `core.llm` seam as the
  verifier (role `filter`). Own contract in `schemas.py` (single-stage, lives here).

## Tests
`tests/output_filter.py`, `tests/output_filter_retry.py`.

## Authoritative docs
`docs/architecture/SYSTEM_ARCHITECTURE.md` → Output Filter; ADR
`docs/decisions/accepted/0003-clannon-owns-security-verifier.md`.
