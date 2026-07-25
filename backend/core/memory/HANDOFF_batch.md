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

## RESOLVED (commit `1e81903`, 2026-07-25): the `_traverse` exponential-blowup/crash bug

Fixed, per backend's ruling to defer to resume and red-team the degenerate shapes first
(`proposals/archive/to-backend/2026-07-06_traversal-blowup-and-crash-flag.md`'s `## Response`).

`graph_store.py::_traverse` no longer uses ANY variable-length Cypher pattern (the `[:IMPORTS*1..N]`
that both enumerated every walk exponentially AND was the surface `ALL SHORTEST` crashed on). It's
now a plain in-Python BFS: each hop is one fixed-pattern `MATCH` over the current frontier (the same
query shape already proven safe elsewhere in this module), with early termination once a layer
discovers nothing new. This sidesteps the whole "which Kuzu variable-length keyword is safe" question
rather than answering it — no variable-length pattern means no walk-enumeration blowup and no
`ALL SHORTEST`-style crash surface, by construction.

Red-teamed (`tests/memory_graph_store.py`, new tests): a self-loop, a multi-node cycle, a zero-edge
node embedded in an otherwise-cyclic graph (**the precise shape that crashed `ALL SHORTEST`**), and a
40-node cyclic+chorded graph at the full `MAX_HOPS_CEILING` with a wall-clock assertion (<5s) as a
real regression guard, not just "didn't hang the test runner."
`tests/memory_graph_manager.py::test_build_code_graph_over_real_backend_then_depends_on_through_port`
(the regression gate the flag named) is **un-skipped** and passes in ~6s — it previously exceeded two
minutes. Also fixed an unrelated stale pinned-import assertion in
`tests/benchmarks/c2_repo_intelligence.py` (pre-existing drift from the manager.py split, 013ea90 —
surfaced only because un-skipping the test above ran this benchmark for the first time in a while).

Full targeted suite: 294 passed, 10 skipped (qdrant-unreachable only — the `_traverse` deselect is
gone).

## Step 4: DONE (commit `809ec72`, 2026-07-25) — the memory extractor

Built per the ratified design (§3.1), resumed after the ~2.5-week pause. Full detail in
`reports/memory/report_v28.md`; summary:
- `writer.py::extract_entities(content) -> ExtractedEntities` — the fail-closed LLM step,
  sibling to `judge_supersession` (same shape/discipline). New prompt `prompts/memory/
  entities.md`, registered as `memory_entities` in `prompts/registry.yaml`.
- `write_policy.py::_write_graph_twin`, hooked into `_persist_one` (**fresh insert only** —
  `point_id is None` before the upsert; a dedup-merge reuses the same vector_id, and
  Fact/Claim `content` is create_only, so re-extracting on a merge is pure waste), gated on
  **`kind ∈ {FACT, ASSUMPTION, DECISION}`** (kind, not tier — DECISION is EPISODIC but still
  gets a twin). Builds `ENTITY` nodes (converged by normalized `canonical_name`), one
  `FACT`/`CLAIM` node (`DECISION`/`FACT` → `FACT`; `ASSUMPTION` → `CLAIM`) with `vector_id` =
  the memory's own point id, `RELATES_TO` edges entity↔fact and entity↔entity, `AUTHORED_BY`
  for each name in `participants`. All node ids minted via `graph_store.node_id(scope, key)`
  (the same formula `GraphManager.write()` uses internally) so edges land correctly. Written
  via `graph_manager.manager.write()` — no foundation change needed.
- Best-effort throughout, identical discipline to `_maybe_mark_superseded`: any fault (LLM
  timeout/error, graph write fault) is logged and never surfaces into the turn.
- `tests/memory_extractor.py` — 20 new tests (extractor contract, twin orchestration,
  end-to-end kind+fresh-insert gating). Full targeted suite: 289 passed, 11 skipped
  (unchanged skip set), zero regressions.

**Not built (deliberately, per the design's own scoping):**
- §3.2 (the contradiction judge, `writer.py::judge_contradiction`) — rides on top of the
  extractor now that it exists; not yet started.
- §3.3 (code symbol tier) / §3.4 (media extractor) — NOT this thread's build; orchestration's
  / the media pipeline's, once this substrate is proven.

## §3.2 DONE (commit `9afef44`, 2026-07-25): the contradiction judge

`writer.py::judge_contradiction` (exact copy of `judge_supersession`'s fail-closed shape) +
`write_policy.py::_judge_contradictions` (the "shares an ENTITY" candidate funnel — never an
all-pairs compare) ride on top of the memory extractor: a fresh ASSUMPTION-kind write's CLAIM
twin gets checked against every existing CLAIM connected to the same entity/entities (via
`GraphPort.members()`/`edges_of()`), bounded to `_MAX_CONTRADICTION_CANDIDATES` (5) judge calls.
A confirmed pair gets a `CONTRADICTS` edge via a second `write()` call. FACT/DECISION twins never
trigger this (CONTRADICTS is homogeneous Claim-to-Claim). 15 new tests in
`tests/memory_extractor.py`. Full detail: `reports/memory/report_v30.md`.

## The exact next step

Everything self-assigned from the resume proposal plus §3.2 is DONE. Remaining candidates per the
ratified design's own order (none started, none assigned yet — check `proposals/to-memory/` first,
backend may have queued something newer):
- **§3.3 — code symbol tier** and **§3.4 — media extractor**: NOT this thread's build per the
  design's own scoping (orchestration's tree / the media pipeline's, once this substrate is
  proven — which it now is, via the memory extractor + contradiction judge).
- **EdgeLabel.CALLS** (§1.4, deferred): only lands in `foundation/contracts/graph.py` when its
  first real consumer (the code extractor) is actually built — propose-up to backend when that
  day comes, per LAW 1 (no speculative foundation surface).
- **The `vector_id` fusion read hop** (§1.5): `GraphPort.lookup(scope, vector_id=X)` is designed
  in but inert (`graph_manager.py`'s `lookup()` already has the "not set yet" branch) — every
  FACT/CLAIM/ENTITY node written by the extractor now carries a real `vector_id`, so this is
  ready to wire up whenever a consumer actually needs the vector→graph hop. Not needed yet.
- **CB2/CB3/EB3 benchmark proofs** (`docs/architecture/knowledge_graph/`'s own promise, §5 of the
  ratified design) — none of the three harnesses (`tests/benchmarks/cb2_*`/`cb3_*`/
  `eb3_cross_media_synthesis.py`) exist yet. Worth considering as the next pick: the substrate +
  both extraction passes are now real and tested, so a benchmark proving CB2/CB3 end-to-end
  (not just unit-level) is the natural next validation step, if backend agrees it's the priority.

## Where to look first when resuming

1. `proposals/to-memory/` — check for anything new before assuming this handoff is current.
2. `proposals/to-backend/2026-07-06_traversal-blowup-and-crash-flag.md` — check its `Status`.
   If backend has ruled on `_traverse`, read the ruling before starting the fix.
3. `git log --oneline -5` in `backend/` — confirm `809ec72` is still `HEAD`, or see what landed
   since.
4. If nothing new: start step 4 above.
