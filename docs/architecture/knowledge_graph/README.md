# Knowledge Graph

> **Purpose:** The architecture home for Attention Threshold **Pillar 2 —
> Cross-Media Knowledge Graph**: the shared representation where every modality
> contributes to one graph and the same entity across media converges into one
> node.
> **Scope:** The entity/relationship/claim/event/source/evidence substrate, the
> convergence rule, and provenance. It **is intended to be** the connective
> tissue **between** [media](../media/) (producers) and [memory](../memory/)
> (store) — this connective layer is not built yet.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** ⚠️ **PROPOSED — not implemented.** The graph as a connective
> structure is not built; media preprocessing and base memory exist, but entity
> convergence / a graph store do not. Tracked by
> [../../decisions/proposed/0005-cross-media-knowledge-graph.md](../../decisions/proposed/0005-cross-media-knowledge-graph.md).
> **Related:** [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
> (Pillar 2) · [../media/](../media/) · [../memory/](../memory/) ·
> [../repository_intelligence/](../repository_intelligence/) ·
> [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
> (Critical Benchmark 3)

## Why this home exists

Pillar 2 had **no dedicated home** before this document — it was split between
`media/` (which produces representations) and `memory/` (which stores), so "the
graph itself" lived nowhere (audit coverage score: 2/5). That split is exactly
where terminology and ownership drift starts. This README gives the graph one
owner that both sides point to.

## Target model (from the pillar)

Every modality produces, into one shared graph (ATTENTION_THRESHOLD Pillar 2):

```
Entities · Relationships · Claims · Events · Sources · Evidence
```

**Convergence rule:** a `Memory Manager` mentioned in a PDF, an architecture
diagram, and a meeting recording must converge into a **single entity** — not
three isolated summaries (ATTENTION_THRESHOLD, 135–155). Provenance is tracked on
every node/edge.

## Boundaries (who owns what)

- **[media/](../media/)** — *produces* per-modality representations **today**
  (text, transcripts, page renders); entity/relationship extraction is
  **proposed, not yet built** (the `MEDIA_INTELLIGENCE.md` representation layer
  is the target).
- **knowledge_graph/ (here)** — *owns* the convergence rule, the graph schema,
  and cross-modal identity.
- **[memory/](../memory/)** — *stores and retrieves* the resulting knowledge in
  the tiers (semantic especially), behind the MemoryPort.

## Disambiguation note

"Knowledge graph" here is the cross-media reality graph. Do not confuse it with
the `ArtifactStore` (delivered output files) or with the memory vector tiers —
see [../../glossary/TERMS.md](../../glossary/TERMS.md).

## What is NOT claimed

No graph store, entity-convergence, or contradiction-detection across modalities
is built. Do not present Pillar 2 as shipped until Benchmark 3 passes.
