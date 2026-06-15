# 0006 — External prompt-screening libraries (LLM Guard, Rebuff)

> **Status:** rejected
> **Date recorded:** 2026-06-15 (back-filled; decision predates this record)
> **Supersedes / superseded by:** superseded by
> [../accepted/0003-clannon-owns-security-verifier.md](../accepted/0003-clannon-owns-security-verifier.md)
> **Authority:** Tier 7 (ADR).

## Context

When designing input screening, established third-party libraries (LLM Guard,
Rebuff) were candidates for prompt-injection and unsafe-content detection.

## Decision

**Rejected.** Clannon does not use external screening libraries. Security policy
is owned by Clannon, not a third-party dependency. The first-party verifier LLM
adjudicates content (ADR 0003).

## Why rejected

- **Ownership of security policy is part of the product's trust story** —
  outsourcing it puts the most sensitive decision outside Clannon's control,
  audit, and prompt-hardening process.
- **External libraries set their own policy and update cadence** — a dependency
  change could silently shift Clannon's security posture.
- **The verifier already adjudicates semantics** — a second external screener is
  redundant given a hardened first-party verifier + deterministic hint checks.

## Consequences

- Clannon maintains its own screening prompts and a red-team regression suite.
- No external-library version risk in the security path.

## Source

[../../architecture/SYSTEM_ARCHITECTURE.md](../../architecture/SYSTEM_ARCHITECTURE.md)
→ Verification ("The verifier replaced LLM Guard and Rebuff. External screening
libraries are not used.").
