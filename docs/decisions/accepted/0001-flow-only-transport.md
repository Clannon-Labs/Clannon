# 0001 — Flow is the only inter-stage transport

> **Status:** accepted
> **Date recorded:** 2026-06-15 (back-filled; decision predates this record)
> **Supersedes / superseded by:** —
> **Authority:** Tier 7 (ADR). Reflected as Invariant §III.11.

## Context

A multi-stage agentic pipeline (intake → sanitize → normalize → verify →
orchestrate → filter → deliver) needs a transport between stages. Free-form text
between stages is the default in most agent frameworks, and it is the source of
prompt-injection bleed, lossy handoffs, and untyped contracts that drift.

## Decision

All runtime payloads move between stages through **Flow** — `Flow.load()`,
`Flow.next()`, `Flow.block()`, `Flow.warn()`, `Flow.fail()`. No free-form text
passes between components. Shared payload schemas live in `foundation`; stage
packages own behavior, not transport. Inside a stage, agents/tools/experts
exchange typed contracts, but not every sub-call is wrapped in a Flow.

## Alternatives considered

- **Free-form text handoff** — rejected: untyped, injectable, lossy, undebuggable
  across stages.
- **A message bus / event schema per pair of stages** — rejected as heavier than
  needed and prone to divergence; a single transport primitive is simpler to
  audit.

## Consequences & risks

- Every stage boundary is typed and inspectable; security gates can reason about
  structured payloads.
- New stages must adopt Flow rather than inventing their own handoff.
- Risk: temptation to smuggle prose inside a Flow field — guard against it in
  review.

## Source

[../../architecture/SYSTEM_ARCHITECTURE.md](../../architecture/SYSTEM_ARCHITECTURE.md)
→ Core Architecture; project `CLAUDE.md` → Hard Constraints #1.
