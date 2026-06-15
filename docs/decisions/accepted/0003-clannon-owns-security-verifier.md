# 0003 — Clannon owns its security policy via a first-party verifier

> **Status:** accepted
> **Date recorded:** 2026-06-15 (back-filled; decision predates this record)
> **Supersedes / superseded by:** supersedes the use of external screening
> libraries — see [../rejected/0006-external-prompt-screening-libraries.md](../rejected/0006-external-prompt-screening-libraries.md)
> **Authority:** Tier 7 (ADR). Reflected as Invariant §IV.15.

## Context

Input must be screened for prompt injection, malicious intent, and unsafe or
unsupported content before the orchestrator can act. Off-the-shelf screening
(LLM Guard, Rebuff) was an option, but security policy is core to Clannon's value
and trust story.

## Decision

The **verifier** — a small, fast first-party LLM with a targeted, hardened system
prompt — is the final input gate and the **sole content blocker** for input.
Deterministic regex checks are only hints; the verifier LLM adjudicates.
Structural gates (unsupported modality, missing capability) still hard-block.
Verifier output is always structured, never user-facing prose. The matching
output-side gate is the **output filter**. Security policy is owned by Clannon,
not a third-party dependency.

## Alternatives considered

- **LLM Guard + Rebuff** — rejected; see ADR 0006. External libraries put core
  security policy outside Clannon's control and audit.
- **Deterministic-only screening** — rejected: regex cannot catch semantic
  attacks; it remains as a hint layer.

## Consequences & risks

- Security policy is auditable and owned in one place; the locked verifier/filter
  prompts load from the out-of-git `prompts.secure/` overlay and fail closed in
  production.
- Clannon carries the maintenance burden of its own screening prompts (mitigated
  by a red-team regression suite).

## Source

[../../architecture/SYSTEM_ARCHITECTURE.md](../../architecture/SYSTEM_ARCHITECTURE.md)
→ Verification, Output Filter, Security Model; project `CLAUDE.md` → Hard
Constraints #3.
