# Knowledge Graph

> **Concrete design lives in [`CLANNON_GRAPH_STACK.md`](CLANNON_GRAPH_STACK.md)** — read it
> first. This README is the orientation/ownership note; the stack doc is the canonical
> "what we build." Where they ever differ, the stack doc wins.
>
> **Purpose:** the home for Clannon's **graph stack** — *one* graph substrate that several
> subsystems write into and traverse. It is the representation behind Attention Threshold
> **Pillar 2 (Cross-Media Knowledge Graph)** AND the index behind **Critical Benchmark 2
> (Large Repository Understanding)** AND a richer structure over the existing memory tiers —
> not three disconnected systems.
> **Scope:** the shared **store** (graph + vectors) and its `node↔vector` contract, the
> per-domain **extractors** that feed it, the cross-modal **convergence rule**, and
> provenance.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** ⚠️ **PROPOSED — not built.** The substrate is now **chosen** (Kuzu + Qdrant,
> see below), but no store, extractor, entity-convergence, or contradiction-detection is
> implemented yet. Tracked by
> [../../decisions/proposed/0005-cross-media-knowledge-graph.md](../../decisions/proposed/0005-cross-media-knowledge-graph.md).
> **Related:** [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
> (Pillar 2) · [../media/](../media/) · [../memory/](../memory/) ·
> [../repository_intelligence/](../repository_intelligence/) ·
> [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
> (CB2 + CB3)

## The core decision: one store, three extractors

See [`CLANNON_GRAPH_STACK.md`](CLANNON_GRAPH_STACK.md) for the full rationale. In short:

- **One shared substrate** — **Kuzu** (embedded property-graph DB, Cypher, on-disk, handles
  graphs far bigger than RAM) paired with **Qdrant** (vectors; already running). Every Kuzu
  node carries a `vector_id`; every Qdrant point carries a `node_id`. You **land
  semantically** (Qdrant) then **walk structurally** (Kuzu) — that hybrid is what makes GBs
  feel like butter without scanning everything.
- **Three separate extractors**, because the thing that turns a source into nodes/edges is
  irreducibly different per domain — but they all write through one common
  `add_nodes / add_edges / add_vectors` interface:
  - **Code** (→ CB2 repository intelligence): tree-sitter (fast/fuzzy) + clang/scip-clang
    (precise) + ripgrep fallback.
  - **Media** (→ CB3 / Pillar 2): PySceneDetect, faster-whisper, CLIP, ffmpeg.
  - **Memory** (→ CB1): nomic-embed-text + spaCy/LLM entity-relation extraction; the existing
    four tiers (wiki/semantic/episodic/procedural) become **node labels in the same store**.

So a code node, a memory fact, and a video shot live in **one graph** and can link to each
other. Build the substrate once; add extractors as separate modules behind the shared writer.

## Convergence rule (Pillar 2)

A `Memory Manager` mentioned in a PDF, an architecture diagram, and a meeting recording must
converge into a **single entity** — not three isolated summaries (ATTENTION_THRESHOLD,
135–155). Provenance is tracked on every node/edge. Node/edge vocabulary across domains:
`Entities · Relationships · Claims · Events · Sources · Evidence` plus the per-domain nodes
the stack doc lists (functions/structs/files; shots/transcript-segments/speakers; facts).

## Boundaries (who owns what)

- **[media/](../media/)** — *produces* per-modality representations (text, transcripts, page
  renders) that the **media extractor** turns into nodes/edges. Entity extraction here is
  proposed, not built.
- **[repository_intelligence/](../repository_intelligence/)** — *uses* the **code extractor**
  + the shared store to navigate large codebases (it is not a separate graph; same substrate).
- **knowledge_graph/ (here)** — *owns* the shared store, the `node↔vector` contract, the
  common writer interface, the convergence rule, and cross-modal identity.
- **[memory/](../memory/)** — its tiers become **node labels in the shared Kuzu store** and it
  shares the same Qdrant; retrieval still flows through the MemoryPort. The graph is a richer
  index **over** memory, **not** a separate store downstream of it.

## Disambiguation note

"Knowledge graph" here is the shared reality/index graph (code + media + memory). Do not
confuse it with the `ArtifactStore` (delivered output files) — see
[../../glossary/TERMS.md](../../glossary/TERMS.md).

## What is NOT claimed

No store, extractor, entity-convergence, or contradiction-detection is built. The substrate is
*chosen* (Kuzu + Qdrant), not *stood up*. Do not present Pillar 2 (or CB2) as shipped until the
benchmarks pass.
