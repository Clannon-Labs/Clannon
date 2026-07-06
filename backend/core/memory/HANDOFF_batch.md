# Handoff — Kuzu knowledge-web build (CB2/CB3/EB3)

Written 2026-07-06, end of session — the owner is pausing all agents (weekly usage limits
nearly out). This supersedes the 2026-07-05 Mission Engine handoff that used to live here (that
thread is long since complete and pushed; superseded content removed, not left to confuse a
fresh reader). Read this first, before checking proposal inboxes.

## Where things stand: committed and pushed, tree clean

```
git log --oneline -3        # (from backend/)
24914b5 feat(memory): knowledge web substrate — Entity/Fact/Claim/MediaSegment (CB2/CB3/EB3)
77051cc refactor(memory): lift Mission Engine's typed-node/edge mechanism into typed_graph.py
013ea90 refactor(memory): split manager.py into thin door + hydration/write_policy/tiers
```

`git status --short` is empty (root and `backend/`). `main` matches `origin/main` — both commits
above are pushed. **Nothing uncommitted, nothing half-done in the tree.** This is a clean stop,
not a "resume unfinished code" handoff.

## The design this build follows

`proposals/archive/to-backend/2026-07-06_knowledge-web-design-cb2-cb3-eb3.md` — my design
proposal + backend's `## Response` ratifying it. Read that file for the full node/edge model
(`ENTITY`/`FACT`/`CLAIM`/`MEDIA_SEGMENT` + `RELATES_TO`/`CONTRADICTS`/`DERIVED_FROM`/
`AUTHORED_BY`), the convergence rule, and the four-step build order. Two decisions were
ratified there:
- **Fusion direction (§1.5): Option B** — one-directional (graph node → vector via `vector_id`).
  `MemoryItem` stays untouched; no reverse hop (vector → graph) until a concrete consumer needs
  it. Don't add `MemoryItem.point_id` speculatively.
- **`EdgeLabel.CALLS` (§1.4):** shape ratified, but the label itself is **deferred** — it lands
  in `foundation/contracts/graph.py` only when the code-symbol-tier extractor (step 3.3 below)
  actually gets built, per LAW 1 (no speculative foundation surface).

A separate correction (not in the archived proposal — filed after, `proposals/archive/
to-memory/2026-07-06_decision-kind-gate-ratified.md`): the memory-extractor gate (step 4, not
yet built) must be **`kind ∈ {FACT, ASSUMPTION, DECISION}`, not tier-based** — `MemoryKind.
DECISION` exists and CB4 decision records write to the EPISODIC tier, so a tier-based
"SEMANTIC/PROCEDURAL only" gate would silently exclude every decision record and strand
`AUTHORED_BY`. `DECISION` maps to a `FACT` graph node (asserted, same epistemic weight).

## What's built (both commits already pushed)

**Step 1 (`77051cc`):** lifted the generic MERGE-by-id/MERGE-by-connectivity mechanism out of
`mission_graph_store.py` into `typed_graph.py`, parameterized over an injected schema dict.
`mission_graph_store.py` is now a thin schema registration delegating to it.

**Step 2/3 (`24914b5`):** the actual substrate.
- `knowledge_store.py` (NEW) — `Entity`/`Fact`/`Claim`/`MediaSegment` node schemas +
  `RelatesTo`/`Contradicts`/`DerivedFrom`/`AuthoredBy` edge schemas, registered against
  `typed_graph.py`.
- `graph_schema.py` (NEW) — every `CREATE NODE/REL TABLE` DDL statement, split out of
  `graph_store.py` (LAW 2 — the new tables pushed that file past 500 lines).
- `graph_manager.py` — `_TYPED_NODE_STORE`/`_TYPED_EDGE_STORE` route each label to its owning
  store module (`mission_graph_store` vs `knowledge_store`). **No `GraphPort` Protocol change
  was needed** — `members()`/`edges_of()` were already generic over any label.
- `typed_graph.py` gained two real capabilities, both found via direct Kuzu verification
  *before* writing tests (read the commit message / `report_v27.md` for the exact repro steps
  if you need them again): a `TypedNodeSchema.defaults` dict (Kuzu requires every row in an
  UNWIND batch to share the same struct shape — a caller omitting an optional column used to
  silently drop the whole write), and `_resolve_node_tables` (Kuzu can `MATCH` an unlabeled node
  pattern but cannot `MERGE`/`CREATE` a relationship without a concrete label per endpoint — so
  heterogeneous edges like `RELATES_TO` resolve each endpoint's real table first, then group by
  resolved pair before the MERGE).
- `tests/memory_knowledge_store.py` (NEW, 22 tests) — entity convergence, create-only vs.
  mutable fields, `vector_id`-keyed Fact/Claim identity, heterogeneous edge persistence +
  asserted-wins + missing-endpoint no-op + tenant isolation, the `DerivedFrom` fusion point
  meeting a real `Task` node, `delete_user`.
- Two pre-existing tests fixed (they used `NodeLabel.ENTITY`/`EdgeLabel.RELATES_TO` as their
  "still unsupported" example — both are now backed by this build): swapped to
  `NodeLabel.CODE_MODULE`/`EdgeLabel.DEFINES` (genuinely still unbacked today).

**Verification:** full memory-scoped suite (`tests/memory_*.py tests/config_memory.py`) —
**269 passed, 10 skipped** (qdrant-unreachable env-skip), **1 deselected** (see below).

## The one open item: a flagged, NOT-yet-resolved bug in sibling (not knowledge-web) code

`tests/memory_graph_manager.py::test_build_code_graph_over_real_backend_then_depends_on_
through_port` is currently **deselected**, not fixed. Root cause: `graph_store.py::_traverse`
(CB2's file-level `depends_on`/`dependents_of`/`breaks_if_removed` — phase-1 code, nothing this
build touches) has an exponential-blowup bug on `backend/`'s now-larger, cyclic import graph
(measured: 12 hops→0.28s, 16 hops→8.3s, 20 hops/`MAX_HOPS_CEILING` exceeds two minutes — the
bare `*1..N` Cypher pattern enumerates every WALK, not every reachable node, and the reachable
set actually plateaus at 5 hops).

I tried the fix (`ALL SHORTEST`) — confirmed correct AND fast (0.012s, identical result) — but
**it segfaults Kuzu's native library** on a common case (a node with zero incident edges in
scope). Reverted immediately; `_traverse` is back to its original, non-crashing (if slow) form.
Flagged to backend: `proposals/to-backend/2026-07-06_traversal-blowup-and-crash-flag.md` (still
`Status: pending` as of this handoff — no response yet). **Do not re-attempt `ALL SHORTEST`
without red-teaming the zero-edge-node case first** — that's exactly what crashed it. Plain
`SHORTEST` (not `ALL SHORTEST`) was tested for performance only, never for the crash case — its
crash-safety is unknown.

This is genuinely orthogonal to the knowledge-web build (rides `members()`/`edges_of()`/
`write()`, never `_traverse`), so it does NOT block anything below. It's flagged, not owned by
this thread — check the proposal's `Status` before touching `_traverse` again.

## The exact next step

**Step 4 (not started): the memory extractor.** Per the ratified design (§3.1):
- New `writer.py::extract_entities(content) -> ExtractedEntities` — a fail-closed LLM step,
  sibling to the existing `judge_supersession` (same `build_agent(..., output_type=...,
  retries=settings.MEMORY.distill_max_retries)` shape, same "any fault/doubt → empty result,
  never raise" discipline).
- Hook into `write_policy.py::record_write_proposals`, **after** a proposal clears the existing
  confidence gate, gated on **`kind ∈ {FACT, ASSUMPTION, DECISION}`** (see the correction above
  — NOT tier-based; `UNSPECIFIED` stays excluded).
- Produces: `ENTITY` nodes for named things in the content, one `FACT`/`CLAIM` node
  (`DECISION`/`FACT` kind → `FACT` node; `ASSUMPTION` → `CLAIM` node) with `vector_id` = the
  memory's own point id, `RELATES_TO` edges entity↔fact and entity↔entity, `AUTHORED_BY` when
  `participants` (CB4's field) is non-empty. Written via `GraphPort.write()` — best-effort, same
  "never blocks the turn" discipline as `learn()` today.
- Then §3.2 (the contradiction judge, `writer.py::judge_contradiction`, exact copy of
  `judge_supersession`'s fail-closed shape) rides on top of the extractor once it exists.
- §3.3 (code symbol tier) and §3.4 (media extractor) are NOT this thread's build — they're
  orchestration's / the media pipeline's extractors respectively, once this substrate is
  proven with the memory extractor.

No proposal needed to start step 4 — it's already ratified, `core/memory/`-only, no foundation
touch expected (the entity-extraction LLM call is a new prompt/agent, not a contract change).

## Where to look first when resuming

1. `proposals/to-memory/` — check for anything new before assuming this handoff is current.
2. `proposals/to-backend/2026-07-06_traversal-blowup-and-crash-flag.md` — check its `Status`.
   If backend has ruled on `_traverse`, that may unblock re-selecting the deselected test (still
   not this thread's job to fix unless explicitly assigned).
3. `git log --oneline -5` in `backend/` — confirm `24914b5` is still `HEAD`, or see what landed
   since.
4. If nothing new: start step 4 above.
