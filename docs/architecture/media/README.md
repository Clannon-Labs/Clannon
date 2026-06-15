# Media

> **Purpose:** Entry point for how Clannon turns any media into knowledge rather
> than throwaway summaries.
> **Scope:** Modality support, the representation layer, cross-modal embeddings,
> the knowledge graph, provider abstraction, and local-first resilience. The
> *security* of media uploads lives in [../security/](../security/); the
> *memory* the graph feeds lives in [../memory/](../memory/).
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
> (Pillar 2) · [../memory/](../memory/) · [../../glossary/TERMS.md](../../glossary/TERMS.md)

## Contents

- **[MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md)** — the full media-native
  architecture: the Universal Asset model, per-modality representations,
  multi-embedding strategy, capability routing, local model stack, reprocessing
  philosophy, and the ten future-proofing rules.

> Scope note: `MEDIA_INTELLIGENCE.md` is the **aspirational/target** media
> architecture (graph DB, full representation matrix, multi-embedding spaces).
> What is built today is narrower — local preprocessing (PDF text + page
> rendering, whisper/ffmpeg audio+video) feeding the multimodal model. Treat the
> doc as the destination, not a description of current code. The tracked
> proposal is [../../decisions/proposed/0005-cross-media-knowledge-graph.md](../../decisions/proposed/0005-cross-media-knowledge-graph.md).

## Canonical principle

From [../../vision/INVARIANTS.md](../../vision/INVARIANTS.md): **text is a view,
not the truth**; media becomes knowledge; raw assets are forever while
representations are disposable and regenerable; never trust one provider, model,
or embedding space. These are non-negotiable even though the full system is still
being built toward.

## Where it connects in the system architecture

[../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md): Normalization (media
handoff), Sanitization (per-modality workers), and the Media expert under
Experts And Sub-Agents.

## Implementation

- `backend/experts/media/` — the media expert + `preprocess.py` (whisper/ffmpeg).
- `backend/core/normalizer/` — code-only media normalization.
