# Clannon Graph Stack

How to build graphs that let an agent navigate the Linux kernel like butter,
traverse GBs of memory seamlessly, and reason over media — without three
disconnected systems.

---

## The core decision: ONE store, THREE extractors

There is **no single tool that generates all three graph types.** The thing that
turns source into nodes and edges is completely different per domain:

- Code needs a **compiler frontend** (it has to understand syntax + symbols).
- Media needs **perceptual models** (vision/audio).
- Memory needs **embeddings + entity extraction**.

But the thing that *stores and queries* the graph can — and should — be shared.

So the architecture splits cleanly:

```
  CODE extractor ─┐
  MEDIA extractor ─┼──►  ONE graph substrate  (Kuzu + Qdrant)
  MEMORY extractor ┘         exact traversal + semantic jump
```

**Extractors are separate. The store is unified.** Build it this way and a code
node, a memory fact, and a video shot all live in the same graph and can even
link to each other.

---

## The shared substrate (build this first)

Two databases working as a pair. This is the single most important pattern in
the whole doc.

| Role | Tool | Why |
|------|------|-----|
| **Structure** | **Kuzu** | Embedded property-graph DB (like SQLite, no server). Columnar, on-disk, handles graphs far bigger than RAM. Cypher queries. This is your "exact" graph — `who calls this`, `what follows this scene`, `what entity links to what`. |
| **Semantics** | **Qdrant** | You already run it. Vector index for fuzzy jumps — `find code similar to this`, `find the memory relevant to this query`, `find frames like this`. |

**How they link (the key trick):**
Every Kuzu node carries a `vector_id`. Every Qdrant point carries a `node_id`.

- Graph traversal answers *"what is exactly connected to X"*.
- Vector search answers *"what is relevant to X but not directly linked"*.
- You hop between them: vector hit → node_id → traverse the graph; or graph node
  → vector_id → find similar.

This hybrid is what makes GBs feel like butter — you never scan everything. You
land semantically (Qdrant), then walk structurally (Kuzu).

> **Why not networkx?** It's in-memory only — it will die on the kernel. Use
> Kuzu as the store, and pull *small subgraphs* into networkx only when you need
> a graph algorithm (shortest path, centrality) on a slice you already narrowed.

> **Scale-up path:** if you ever outgrow embedded Kuzu (multi-tenant server
> graph, concurrent writers at scale), the swap target is **Neo4j**. Same Cypher,
> so queries port. Don't start there — embedded is simpler and fits Clannon now.

---

## Extractor 1 — Code / Linux kernel

The kernel is the hard case: ~30M lines of C, macro-heavy, function pointers
everywhere, and `#ifdef` means the graph literally changes per build config.
That rules out naive parsers. You need **two tiers**.

### Tier 1 — fast & fuzzy: tree-sitter
- Incremental parser, no compile step, every language.
- Gives you syntax trees instantly — definitions, rough structure, breadth.
- **Limitation:** it does *not* resolve macros or function pointers. It's the
  cheap first pass, not the source of truth.

### Tier 2 — slow & correct: clang-based
This is non-negotiable for the kernel. Only a real compiler frontend resolves
kernel symbols correctly.

- **scip-clang** — batch-indexes the whole repo into a precise symbol graph
  (SCIP format) → load that into Kuzu. This is your "build the kernel graph" step.
- **clangd** — the LSP server, for *interactive* precise lookups (go-to-def,
  find-all-references) when the agent is actively exploring.

Both need a **compilation database** (`compile_commands.json`):
```bash
# Modern kernel can emit it directly:
make compile_commands.json
# Generic C project fallback:
bear -- make
```

### Raw fallback: ripgrep (`rg`)
When there's no build, no index, or you just need a text hit fast. Always keep it
in the toolbox.

### What goes in the graph
- **Nodes:** functions, structs, files, macros, ops-structs.
- **Edges:** `calls`, `defined_in`, `includes`, `references`.
- **Vectors (Qdrant):** embed each function/file chunk so the agent can find
  *semantically related* code, not just call-connected code.

### The honest limit
Static analysis **cannot fully resolve function pointers** — and the kernel runs
on them (every `->ops` struct). Your call graph will be precise for direct calls
and incomplete for indirect ones. No tool fixes this fully; accept it and let the
agent fall back to ripgrep + reasoning for the dynamic cases.

---

## Extractor 2 — Media

A media graph is **temporal**: segments and entities over time. Different
extractors per modality, all writing into the same Kuzu + Qdrant store.

| Need | Tool | Output |
|------|------|--------|
| Cut video into shots/scenes | **PySceneDetect** | shot boundary nodes |
| Transcribe audio | **faster-whisper** *(already in stack)* | timed text segments |
| Frame / image embeddings | **CLIP** (via `open_clip` or sentence-transformers) | visual vectors → Qdrant |
| Extract frames/audio | **ffmpeg** *(already in stack)* | the raw inputs for the above |
| (optional) who-spoke-when | **pyannote.audio** | speaker nodes |

### What goes in the graph
- **Nodes:** shots, transcript segments, speakers, detected objects/faces.
- **Edges:** `follows` (temporal), `appears_in`, `spoken_by`.
- **Vectors:** CLIP for frames, text embeddings for transcript → "find the part
  where X happens" works by semantic search, then you walk the timeline in Kuzu.

This is what lets the agent answer *"find the scene where they discuss pricing"*
— Qdrant finds the transcript segment, Kuzu walks to the surrounding shots.

---

## Extractor 3 — Memory

This overlaps heavily with your existing memory system — same Qdrant, same
`nomic-embed-text`. The graph layer just adds **structure between facts**.

| Need | Tool | Output |
|------|------|--------|
| Embed facts/memories | **nomic-embed-text** *(already in stack)* | vectors → Qdrant |
| Pull entities & relations from text | **spaCy** (fast) or an **LLM pass** (richer) | entity + relation nodes |

### What goes in the graph
- **Nodes:** entities (people, projects, concepts), facts, claims.
- **Edges:** `relates_to`, `authored_by`, `contradicts`, `derived_from`.
- **Vectors:** the fact embeddings you already store.

Your four memory tiers (wiki/semantic/episodic/procedural) become **node labels**
in Kuzu — the graph is just a richer index over memory you already have.

---

## Overlaps — what's shared vs separate

| Layer | Shared across all 3? | Notes |
|-------|----------------------|-------|
| **Graph store (Kuzu)** | ✅ Shared | One DB, different node labels per domain |
| **Vector store (Qdrant)** | ✅ Shared | One service, different collections |
| **Hybrid pattern** (land by vector → walk by graph) | ✅ Shared | Identical retrieval logic everywhere |
| **node↔vector linking** | ✅ Shared | Same `node_id`/`vector_id` convention |
| **Extractor** | ❌ Separate | Compiler vs perceptual models vs entity extraction — cannot be unified |
| **Embedding model** | ⚠️ Partial | Code + memory can share a text embedder; **media needs CLIP (visual) + whisper (audio)** — different by nature |

**Bottom line:** one store, one retrieval pattern, three irreducibly different
front-ends feeding it. Build the substrate once; add extractors as separate
modules behind a common "write nodes + edges + vectors" interface.

---

## The minimal robust set (what you actually install)

**Substrate (build first):**
- `kuzu`
- `qdrant` *(already running)*

**Code / kernel:**
- `tree-sitter` (+ language grammars)
- `scip-clang` (batch index) and `clangd` (interactive)
- `bear` (for `compile_commands.json` on non-kernel projects)
- `ripgrep`

**Media:**
- `scenedetect` (PySceneDetect)
- `faster-whisper` *(already in stack)*
- `open_clip_torch` *or* `sentence-transformers` (CLIP)
- `ffmpeg` *(already in stack)*
- `pyannote.audio` *(optional — diarization)*

**Memory:**
- `nomic-embed-text` via Ollama *(already in stack)*
- `spacy` *(or reuse an LLM pass for relation extraction)*

**Algorithms on slices (optional):**
- `networkx` — only for running graph algorithms on subgraphs you've narrowed,
  never as the store.

---

## One-paragraph build order

1. Stand up **Kuzu** next to **Qdrant**; define the `node_id ↔ vector_id` contract.
2. Write one **graph-writer interface** (`add_nodes`, `add_edges`, `add_vectors`).
3. Build the **code extractor** first (tree-sitter pass → scip-clang precise pass
   → writer). Prove it on a mid-size repo before pointing it at the kernel.
4. Add the **media** and **memory** extractors as separate modules against the
   same writer.
5. Build the **hybrid query** helper (vector search → node_id → Cypher traversal)
   — this one function is what every expert calls.
