# core/verifier/ — the final input gate, sole input content blocker

Owns the last gate before orchestration: deterministic handoff/routing checks,
then a small fast LLM for semantic attack screening.

## NEVER
- Verifier output is ALWAYS structured (`VerificationResult`); it NEVER produces
  user-facing prose (invariant §IV.15).
- Deterministic regex is a HINT only — it records a score / `suspected` flag, it
  must NOT content-block. The verifier LLM adjudicates every text/PDF input that
  clears the structural checks; it is the sole content blocker before the
  orchestrator. (Structural gates — unsupported modality, missing capability —
  still hard-block.)
- Don't weaken the system prompt. `verifier` is a `locked` security-boundary
  prompt: the real hardened text lives out-of-git in `prompts.secure/verifier/system.md`;
  the committed `prompts/verifier/system.md` is only the dev/CI baseline. Prod fails
  closed (`VRAKSHA_REQUIRE_PROD_PROMPTS=1`) if the locked prompt rides its baseline.
- Infra/config faults → `flow.fail` (fail hard). Threats → `flow.block`.

## Conventions
- `verifier.py` is the door; deterministic checks in `checks.py`/`rules.py`, the
  LLM pass in `agent.py`, own contracts in `schemas.py` (single-stage — they live
  here, not in foundation). Categories map to `BlockReason` (injection →
  `INJECTION_DETECTED`, unsupported → `UNSUPPORTED_MODALITY`).

## Tests
`tests/verifier.py`; red-team regression `scripts/prompt_regression.py`.

## Authoritative docs
`docs/architecture/SYSTEM_ARCHITECTURE.md` → Verification; ADR
`docs/decisions/accepted/0003-clannon-owns-security-verifier.md`.
