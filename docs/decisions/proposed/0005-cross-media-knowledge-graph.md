# 0005 — Cross-media knowledge graph (media becomes knowledge)

> **Status:** proposed
> **Date recorded:** 2026-06-15
> **Supersedes / superseded by:** —
> **Authority:** Tier 7 (ADR). The *principle* (media becomes knowledge) is
> Invariant §VI.25; the *full graph implementation* below is a target, not yet
> built, hence "proposed."

## Context

The Attention Threshold's Pillars 2 and 3 require that all modalities (PDF,
image, audio, video, code) converge into one shared representation, and that
repositories larger than a context window be reasoned about without prompt
stuffing. The full media architecture (`architecture/media/MEDIA_INTELLIGENCE.md`)
describes a Universal Asset model, per-modality representations, multi-embedding
spaces, and a dedicated graph database (e.g. Neo4j) holding reality
relationships. Today's build is narrower: local preprocessing (PDF text + page
rendering, whisper/ffmpeg) feeding the multimodal model.

## Decision (proposed)

Build toward the cross-media knowledge graph as specified in the media
architecture: every modality produces entities/relationships/claims/events/
sources/evidence into a shared graph; the same entity across modalities converges
into one node; raw assets are preserved so representations can be regenerated.
**The graph DB choice, embedding-space matrix, and rollout sequence are not yet
ratified** — this ADR records the intent and the open questions, pending founder
sign-off and a path that satisfies the Attention Threshold benchmarks.

## Alternatives considered

- **Per-modality summaries stored separately** — explicitly forbidden by the
  media architecture; loses cross-modal reasoning (the whole point).
- **Vectors only, no graph** — insufficient for "what depends on Y / what breaks
  if X is removed" repository-intelligence questions.

## Consequences & risks

- Unlocks Critical Benchmarks 2 (large repo understanding) and 3 (unified
  multi-modal representation) and Exceptional Benchmark 3.
- Significant scope; risk of over-building ahead of a demonstrable slice. The
  Attention Threshold's "demonstration first" rule applies — build the
  demonstrable slice first.

## Source

[../../architecture/media/MEDIA_INTELLIGENCE.md](../../architecture/media/MEDIA_INTELLIGENCE.md);
[../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
→ Pillars 2 & 3; [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
→ Critical Benchmarks 2–3.
