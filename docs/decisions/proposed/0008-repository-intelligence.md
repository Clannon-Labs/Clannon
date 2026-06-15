# 0008 — Repository Intelligence (Pillar 3)

> **Status:** proposed
> **Date recorded:** 2026-06-15
> **Supersedes / superseded by:** —
> **Authority:** Tier 7 (ADR). Anchors the proposed home
> [../../architecture/repository_intelligence/](../../architecture/repository_intelligence/).

## Context

Attention Threshold Pillar 3 requires reasoning about repositories larger than a
context window (ATTENTION_THRESHOLD.md, 165–215), and Critical Benchmark 2 tests
it. An audit found this pillar had **no architecture home, no code, and no ADR** —
the worst pillar-coverage gap (score 1/5). A named pillar with zero ownership is
an architectural-truth gap: nothing records what it should be or that it isn't
built.

## Decision (proposed)

Adopt `architecture/repository_intelligence/` as the home for this pillar and
record the target as graph-backed repository reasoning (file / dependency /
architectural / decision / ownership graphs), explicitly **forbidding**
prompt-stuffing. The graph DB choice, ingestion pipeline, and rollout sequence
are **not yet ratified** — this ADR records intent + ownership, pending a
demonstrable slice (the Attention Threshold "demonstration first" rule applies).

## Alternatives considered

- **Leave it homeless / implicit in the code expert** — rejected: invisible to
  new contributors, no traceability, drift risk; the pillar effectively vanishes.
- **Fold entirely into `knowledge_graph/`** — rejected: repository intelligence
  is a distinct capability with its own benchmark; it *shares* the graph
  substrate but answers code-architecture questions specifically. Cross-linked
  instead.

## Consequences & risks

- Pillar 3 becomes traceable and honestly marked unbuilt.
- Risk: a home for an unbuilt capability can imply it exists — mitigated by the
  prominent PROPOSED banner and "what is NOT claimed" section in the README.

## Source

[../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
→ Pillar 3; [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
→ Critical Benchmark 2.
