# Decisions (ADRs)

> **Purpose:** Preserve the *reasoning* behind the architecture over time, so no
> agent re-litigates a settled decision and no decision lives only in code.
> **Scope:** Lightweight Architecture Decision Records — one decision per file,
> sorted by lifecycle status into subfolders.
> **Authority level:** Tier 7 (cross-cutting record). An **accepted** ADR is
> authoritative for the single decision it records, but is subordinate to the
> Invariants, the Attention Threshold, Goals, and the System/Subsystem
> architecture. If an ADR conflicts with a higher tier, the higher tier wins and
> the ADR is updated or deprecated.
> **Related:** [../00_START_HERE.md](../00_START_HERE.md) ·
> [../vision/INVARIANTS.md](../vision/INVARIANTS.md) ·
> [../architecture/SYSTEM_ARCHITECTURE.md](../architecture/SYSTEM_ARCHITECTURE.md)

## Why decisions are recorded

The architecture documents say *what* the system is. ADRs say *why it is that
way* — what alternatives existed, what was rejected, what risks were accepted.
This is a direct application of two Invariants: **no critical decision lives only
in code**, and **institutional memory (decisions) outranks conversation memory**.
The product itself is built to preserve decision reasoning; its own docs must
model that.

## Decision lifecycle

Each ADR lives in exactly one folder reflecting its current status:

| Folder | Meaning |
|---|---|
| `proposed/` | Under consideration. Reasoning is captured; not yet binding. |
| `accepted/` | Decided and in force. Authoritative for its scope. |
| `rejected/` | Considered and explicitly turned down. Kept so it is not re-proposed. |
| `deprecated/` | Was accepted, now superseded. Kept for the historical reasoning. |

A decision moves by being **relocated** between folders (and its status header
updated), never deleted — that is how reasoning survives. When an accepted ADR is
superseded, move it to `deprecated/` and link the ADR that replaced it.

## How agents should use decisions

1. **Before proposing an architectural change**, search `decisions/` (all four
   folders). If `accepted/` already settles it, follow it. If `rejected/` already
   turned your idea down, read why before re-raising it.
2. **When making a new architectural decision**, record it as an ADR in the same
   pass — an Invariant requires it. Start it in `proposed/` if it needs founder
   sign-off, or `accepted/` if the founder has already decided.
3. **When you find a decision that exists only in code or chat**, write the ADR
   for it. Back-filling is encouraged.
4. **Never silently contradict an accepted ADR.** Supersede it with a new ADR and
   move the old one to `deprecated/`.

## File format

Copy [TEMPLATE.md](TEMPLATE.md). Name files `NNNN-kebab-title.md` with a
zero-padded sequence number. Keep them short: the value is the reasoning, not
length.

## Index of recorded decisions

**Accepted**
- [0001-flow-only-transport.md](accepted/0001-flow-only-transport.md)
- [0002-single-qdrant-userid-scoping.md](accepted/0002-single-qdrant-userid-scoping.md)
- [0003-clannon-owns-security-verifier.md](accepted/0003-clannon-owns-security-verifier.md)
- [0004-redis-enforces-postgres-truths-budget.md](accepted/0004-redis-enforces-postgres-truths-budget.md)

**Proposed**
- [0005-cross-media-knowledge-graph.md](proposed/0005-cross-media-knowledge-graph.md)
- [0008-repository-intelligence.md](proposed/0008-repository-intelligence.md)
- [0009-agent-civilization-artifact-protocol.md](proposed/0009-agent-civilization-artifact-protocol.md)

**Rejected**
- [0006-external-prompt-screening-libraries.md](rejected/0006-external-prompt-screening-libraries.md)

**Deprecated**
- [0007-macondo-checkpoint-build-phase.md](deprecated/0007-macondo-checkpoint-build-phase.md)

> This seed set captures the largest decisions already implied by the
> architecture. It is **not** exhaustive — back-fill more as you find them.
