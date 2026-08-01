# Memory Architecture

Memory is Vraksha's moat: the system that makes run N+1 smarter than run N.
This document is the authoritative design for the memory layer alone. The
system-wide rules it inherits (Flow transport, MemoryPort as the only door,
wiki-beats-everything) live in the root architecture doc and are not restated.

---

## 1. Identity model — every ID and where it's used

Identity is set ONCE at the entry point and travels in Flow context. Memory
never derives identity from content, model output, or retrieved data.

| ID | Set where | Used by memory for |
|---|---|---|
| `user_id` | Entry point (CLI env / server session cookie) → `Flow.new(..., user_id=)` → `ctx.user_id` | **The mandatory scope.** Every vector carries it in its payload; every search filters on it. Cross-user reads are impossible at the query level, not the convention level. |
| `session_id` | Entry point → `ctx.session_id` (CLI: `"cli"`; server: the run id) | Stored in payloads for session-level recall ("earlier in this session") and write provenance. Never used as a search scope on its own — always AND-ed under `user_id`. |
| `trace_id` | `Flow.new()` (uuid4 per request) → `ctx.trace_id` | Write provenance: which request produced a memory. Joins memory entries to the decision-log audit trail. |
| `memory_id` | Memory manager at write time (`uuid4`) | Qdrant point ID. Stable handle for dedup-updates, deletion (user right-to-erasure), and provenance references. |
| `span_id` | Flow journal per stage | Not stored — memory is below span granularity. |

The port carries identity explicitly through `HydrationRequest` and
`MemoryTurn`; list/delete take authenticated scope directly. A request without
`user_id` is refused (empty hydration/listing, rejected write/delete). Curator
tools capture trusted turn scope and never accept identity arguments.

## 2. Tiers

One Qdrant collection per tier — shared across all users, scoped by payload
filter (never per-user collections).

| Tier | Collection | Written by | Trust | Content |
|---|---|---|---|---|
| Wiki | `vraksha_wiki` | User only (via delivery layer sync) | 3 (highest) | User-authored .md knowledge |
| Semantic | `vraksha_semantic` | Manager curator + policy | 2 | Durable facts/claims with provenance + confidence |
| Episodic | `vraksha_episodic` | Manager curator + policy | 1 | Meaningful outcomes, decisions, failures, milestones — never transcripts |
| Procedural | `vraksha_procedural` | Manager curator + policy | 1 | Stable preferences, habits, repeatable workflows |

`WORKING` memory (current turn) never reaches Qdrant — it lives on `ctx`.

**Trust is a hard ordering at hydration:** when contents conflict the higher
trust tier wins placement; wiki items are never displaced by inferred items.

## 3. Point schema (every tier identical)

```
id:      memory_id (uuid4)
vector:  768-dim nomic-embed-text-v1.5 (fastembed, local ONNX)
payload: {
  user_id:    str   # MANDATORY — indexed, the scope
  session_id: str   # provenance + session recall
  trace_id:   str   # provenance → decision log
  saved_by:  str   # trusted MemorySaver; curator writes memory_curator
  tier:       str   # redundant with collection; guards bulk ops
  content:    str   # the memory text (embedded text == stored text)
  rationale:  str   # why the writer proposed it
  confidence: float # writer's confidence (0..1)
  trust:      int   # tier trust at write time
  created_at: float # unix ts — recency decay input
  # typed-knowledge (CB1) — additive; legacy points omit these keys and read
  # back as the contract defaults (unspecified / 0.0 / "") via `.get(default)`.
  kind:          str   # MemoryKind: fact | assumption | unspecified (legacy/untyped)
  valid_at:      float # unix ts the fact became true (vs created_at = when learned); 0 = unknown
  source:        str   # source-document attribution; "" = agent inference
  superseded_by: str   # memory_id of the record replacing this; "" = current (EB1 sets this — inert in CB1)
  participants:  str   # trusted completed-turn participants
}
```

`user_id` and `session_id` get Qdrant keyword payload indexes at collection
creation. The `user_id` index is marked `is_tenant=true` (Qdrant's documented
multi-tenancy layout): points are physically grouped per tenant, so scoped
queries stay fast at scale. Pre-existing collections are upgraded in place on
first use.

## 4. Hydration (read path)

`hydrate(HydrationRequest)` → `HydrationPackage` is the deterministic fast path,
started before verification and resolved before planning. Steps:

1. **Scope check** — no `user_id` → empty package with a note. Fail closed.
2. **Embed** the normalized query text (one embedding call, cached model).
3. **Per-tier search** — each allowed tier, top-K (`settings.MEMORY.search_top_k`,
   default 10), filtered `user_id == request.user_id`. Tiers the caller's plan
   doesn't include are simply not searched (`allowed_tiers` on the request;
   default: all). A **relevance floor** (`settings.MEMORY.relevance_floor`,
   default 0.30) drops hits below that raw cosine *before* ranking, so weak
   neighbours never fill context.
4. **Score** = cosine similarity × recency decay (half-life 30 days,
   floor 0.5) — old memories fade but never vanish.
5. **Lagrangian budget allocation** across tiers (the root doc's model):
   maximize Σ relevance·tokens s.t. Σ tokens ≤ budget, tokens_tier ≥ min_tier.
   Implementation: water-filling — every non-empty tier gets its minimum
   floor (wiki 25%, others 15% of budget), the remainder goes to tiers in
   proportion to their mean item relevance; items pack per-tier best-first under a
   real `tiktoken` (cl100k_base) token count — char heuristic only as fallback —
   until the tier budget is spent.
6. **Assemble** `HydrationPackage` ordered by (trust desc, score desc) so the
   prompt renders wiki → semantic → episodic/procedural.

Default token budget: 2000 when the request doesn't set one.

### Conditional deep retrieval

Fast hydration remains the `MemoryPort.hydrate()` contract and never calls a
generative model. After the verifier passes, memory's `prefetch.collect` may call the
Manager-internal `deepen(request, fast)` for explicit decision-history, provenance,
supersession, trade-off, risk, or multi-facet continuity questions.

The bounded reader can reach memory only through its per-run `search_memory` closure.
That tool captures authenticated `user_id` and server-decided `allowed_tiers`; neither
appears in the model schema. It searches only those tiers, normalizes store hits into
safe provenance-bearing candidates, drops mismatched tenant payloads, and gives each
candidate an opaque run-local id. Final structured output may select only ids the tool
returned. Generated prose never becomes hydration context.

Reader limits: four searches, six candidates per search, six final selections, five
agent turns, 350 output tokens, and the memory read wall-clock timeout. Reader/tool/
prompt/store failure preserves fast context and marks the package honestly degraded.
Clearly simple hydration and any fast-path store degradation add zero reader calls.
The original token budget still caps the merged package.

## 5. Manager-owned curation and write policy

`process_turn(MemoryTurn)` receives neutral, completed-turn evidence after
delivery. Orchestrator and experts do not select tiers, construct durable
writes, or access storage. Manager's bounded LLM gets two internal typed tools:

- `search_memory` searches existing inferred memory under captured `user_id`;
- `save_memory` stages one SEMANTIC, EPISODIC, or PROCEDURAL action.

Staging is not persistence. Actions remain buffered until curator returns a
successful final verdict; any model/tool fault discards them all. Code owns
scope, call/content/list bounds, non-empty rationale, confidence gates,
epistemic typing, source-backed facts, transcript rejection, trusted
`saved_by=memory_curator`, dedup, and supersession. Model alone decides future
relevance and inferred tier; most turns correctly stage nothing.

- **Wiki / Working**: unrepresentable as curator tiers.
- **Dedup**: before insert, search the target tier for the same user with
  similarity ≥ 0.97; on a near-duplicate, refresh that point (created_at,
  confidence = max) instead of inserting. Memories converge, never multiply.
  The refresh keeps the **stronger typed signal**, symmetric with confidence:
  `kind` never downgrades (fact > assumption > unspecified), and a non-empty
  `source` / `valid_at` is not wiped by a barer re-write.
- **Typing**: curator sets `fact`, `assumption`, or `decision`; policy refuses
  `unspecified`. `superseded_by` remains manager-owned.
- Content is capped at 2,000 chars before embedding.

`record_write_proposals` and `learn` remain internal compatibility helpers for
benchmarks/tooling during caller migration. Neither is in `MemoryPort`.

Writes happen post-delivery in the pipeline order, and a write failure NEVER
fails the run (logged, dropped).

## 6. Listing and deletion

`list_entries(user_id)` performs bounded tenant-filtered Qdrant scrolls across
all inferred tiers and returns real points with stable IDs and provenance.
`delete_entry(user_id, memory_id)` checks ownership inside the store door.
Missing and foreign ids both return `False`.

## 7. Failure model — memory never takes a run down

Memory is augmentation, not a gate. Every failure degrades, none block:

| Failure | Behaviour |
|---|---|
| Qdrant unreachable | Hydration: empty package + note. Writes: dropped with a logged warning. Pipeline proceeds. |
| Embedding model unavailable | Same degradation; the model loads lazily and is retried next call. |
| Deep reader/model unavailable | Keep deterministic fast context; mark deep retrieval unavailable. |
| Collection missing | Auto-created on first use (idempotent ensure). |
| Oversized/empty content | Truncated / skipped at the policy layer. |

A one-shot circuit breaker memoizes "Qdrant down" for 30s so a dead store
costs one timeout per window, not one per call.

## 8. Security invariants

1. `user_id` filter is constructed inside the store module — the ONLY place a
   Qdrant query is built. Nothing else imports the qdrant client. (CI Semgrep
   rule for unscoped queries lands with multi-tenancy hardening.)
2. Identity cannot come from the model: curator tools carry no `user_id` field.
   Trusted turn identity is captured by internal tool closures.
3. Defense in depth on reads: every hit returned by a scoped search is
   re-verified against the requested `user_id` in the store; a mismatch is
   dropped and logged as a tenant-isolation violation.
4. Defense in depth on writes: an upsert that names an existing `point_id`
   first verifies the point belongs to the writing user (an upsert REPLACES
   the point, filters don't apply) — foreign ids are refused and logged.
5. Memory content is treated as untrusted on the way in (it originated from
   model output or retrieved web content): capped, plain text only.
6. Wiki ingestion is a separate, user-authenticated path (delivery layer →
   manager `sync_wiki()`); inferred writes can never masquerade as wiki.
7. Erasure: `delete_user()` removes every point for a user across all tiers,
   continuing past per-tier faults so one bad collection never leaves the
   others populated (right-to-deletion; called on account deletion).

## 9. Module layout

```
core/memory/
  ARCHITECTURE.md   ← this document
  manager.py        ← MemoryPort implementer; the only door (thin adapter)
  hydration.py      ← read-side: ranking, recency decay, Lagrangian budgeting
  deep_reader.py    ← post-verifier, hard-query LLM retrieval through scoped tools
  curator.py        ← Manager LLM + typed scope-captured search/save tools
  write_policy.py   ← write-side: dedup, EB1 supersession, sync_wiki
  items.py          ← store payload → MemoryItem provenance translator
  tiers.py          ← TIER_TRUST/TIER_FLOOR (shared by hydration + write_policy)
  embeddings.py     ← fastembed nomic-embed-text-v1.5 wrapper (lazy singleton)
  store.py          ← Qdrant access; the ONLY module that builds queries;
                      owns collections, payload indexes, user_id filters
  writer.py         ← bounded post-write enrichment/judgment calls
  graph_store.py / graph_manager.py / mission_graph_store.py / graph_extract.py
                    ← GraphPort implementer (Kuzu) — code-import graph +
                      Mission Engine substrate
  batch_store.py / batch_awareness_manager.py
                    ← BatchAwarenessPort implementer (cross-batch awareness slice)
```

Config via env: `QDRANT_URL` (default `http://localhost:6333`),
`VRAKSHA_MEMORY_DISABLED=1` forces the degraded mode (tests, CI).

## 10. What stays out (for now)

Lagrangian weights learned per user, R2-backed wiki files, and plan-tier
enforcement at this layer (delivery gates tiers through `allowed_tiers`).
