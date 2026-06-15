# Memory

> **Purpose:** Entry point for Clannon's memory system — the moat. How context
> persists, ranks, and rehydrates across sessions.
> **Scope:** The four memory tiers, the Memory Manager, the MemoryPort boundary,
> hydration, Lagrangian budget allocation, and tenancy scoping. Excludes hot
> session cache mechanics (see [../storage/](../storage/)).
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [../../vision/INVARIANTS.md](../../vision/INVARIANTS.md) (§I) ·
> [../storage/](../storage/) · [../agents/](../agents/) ·
> [../../glossary/TERMS.md](../../glossary/TERMS.md)

## Canonical design

This subsystem has **two authoritative documents** — read both:

1. **System-wide rules** — [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md),
   "Memory System": the Memory Manager, the four tiers (Wiki / Semantic /
   Episodic / Procedural), Lagrangian budget allocation, the vector-store
   architecture, and tier-by-subscription access.

2. **Memory-layer deep dive** — **`backend/core/memory/ARCHITECTURE.md`**
   (lives beside the code; referenced by the project's `CLAUDE.md`). This is the
   authoritative design for the memory layer alone — identity model, scoping,
   trust ordering, recency decay, dedup, and write policy. It deliberately does
   *not* restate the system-wide rules above.

> Note: the memory deep dive lives under `backend/` (not in `docs/`) because it
> is code-adjacent and referenced by path in the build instructions. Do not move
> it; link to it.

## Why memory is its own tier of importance

Per [../../vision/INVARIANTS.md](../../vision/INVARIANTS.md): memory is
first-class; institutional memory (decisions, contracts, risks) outranks
conversation; wiki beats everything; episodic is the non-negotiable baseline;
experts never write directly; access is only through the MemoryPort. The
[Attention Threshold](../../vision/ATTENTION_THRESHOLD.md) raises the bar further:
typed knowledge, decision retrieval outranking chat retrieval, and a cross-media
knowledge graph (see [../media/](../media/)).

## Implementation

- `backend/core/memory/` — real 4-tier Qdrant memory behind the MemoryPort door.
- `backend/foundation/` — exposes the `MemoryPort` contract; nothing imports
  memory internals.
