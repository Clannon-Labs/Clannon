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

The port contract carries identity explicitly: `HydrationRequest.user_id` and
`record_write_proposals(user_id=, session_id=, ...)`. A request without a
`user_id` is refused (empty hydration, rejected writes) — fail closed on scope.

## 2. Tiers

One Qdrant collection per tier — shared across all users, scoped by payload
filter (never per-user collections).

| Tier | Collection | Written by | Trust | Content |
|---|---|---|---|---|
| Wiki | `vraksha_wiki` | User only (via delivery layer sync) | 3 (highest) | User-authored .md knowledge |
| Semantic | `vraksha_semantic` | Write policy (confidence ≥ 0.6) | 2 | Facts/claims with provenance + confidence |
| Episodic | `vraksha_episodic` | Write policy (always) | 1 | Run outcomes, decisions, history |
| Procedural | `vraksha_procedural` | Write policy (confidence ≥ 0.6) | 1 | Habits, formats, recurring workflows |

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
  tier:       str   # redundant with collection; guards bulk ops
  content:    str   # the memory text (embedded text == stored text)
  rationale:  str   # why the writer proposed it
  confidence: float # writer's confidence (0..1)
  trust:      int   # tier trust at write time
  created_at: float # unix ts — recency decay input
}
```

`user_id` and `session_id` get Qdrant keyword payload indexes at collection
creation — filters stay fast at scale.

## 4. Hydration (read path)

`hydrate(HydrationRequest)` → `HydrationPackage`, called by the orchestrator
loop before planning. Steps:

1. **Scope check** — no `user_id` → empty package with a note. Fail closed.
2. **Embed** the normalized query text (one embedding call, cached model).
3. **Per-tier search** — each allowed tier, top-K (default 8), filtered
   `user_id == request.user_id`. Tiers the caller's plan doesn't include are
   simply not searched (`allowed_tiers` on the request; default: all).
4. **Score** = cosine similarity × recency decay (half-life 30 days,
   floor 0.5) — old memories fade but never vanish.
5. **Lagrangian budget allocation** across tiers (the root doc's model):
   maximize Σ relevance·tokens s.t. Σ tokens ≤ budget, tokens_tier ≥ min_tier.
   Implementation: water-filling — every non-empty tier gets its minimum
   floor (wiki 25%, others 15% of budget), the remainder goes to tiers in
   proportion to their mean item relevance; items pack per-tier best-first
   under ~4 chars/token estimation until the tier budget is spent.
6. **Assemble** `HydrationPackage` ordered by (trust desc, score desc) so the
   prompt renders wiki → semantic → episodic/procedural.

Default token budget: 2000 when the request doesn't set one.

## 5. Write policy (write path)

`record_write_proposals(user_id, session_id, proposals)` — proposals come from
the orchestrator/experts; the manager alone decides persistence:

- **Episodic**: always accepted (the non-negotiable baseline tier).
- **Semantic / Procedural**: accepted when `confidence ≥ 0.6`.
- **Wiki**: NEVER accepted from proposals — wiki is user-authored only;
  a proposal targeting wiki is downgraded to semantic.
- **Dedup**: before insert, search the target tier for the same user with
  similarity ≥ 0.97; on a near-duplicate, refresh that point (created_at,
  confidence = max) instead of inserting. Memories converge, never multiply.
- Content is truncated to 2,000 chars before embedding (defensive cap).

Writes happen post-delivery in the pipeline order, and a write failure NEVER
fails the run (logged, dropped).

## 6. Failure model — memory never takes a run down

Memory is augmentation, not a gate. Every failure degrades, none block:

| Failure | Behaviour |
|---|---|
| Qdrant unreachable | Hydration: empty package + note. Writes: dropped with a logged warning. Pipeline proceeds. |
| Embedding model unavailable | Same degradation; the model loads lazily and is retried next call. |
| Collection missing | Auto-created on first use (idempotent ensure). |
| Oversized/empty content | Truncated / skipped at the policy layer. |

A one-shot circuit breaker memoizes "Qdrant down" for 30s so a dead store
costs one timeout per window, not one per call.

## 7. Security invariants

1. `user_id` filter is constructed inside the store module — the ONLY place a
   Qdrant query is built. Nothing else imports the qdrant client. (CI Semgrep
   rule for unscoped queries lands with multi-tenancy hardening.)
2. Memory content is treated as untrusted on the way in (it originated from
   model output or retrieved web content): capped, plain text only.
3. Wiki ingestion is a separate, user-authenticated path (delivery layer →
   manager `sync_wiki()`); inferred writes can never masquerade as wiki.
4. Erasure: `delete_user()` removes every point for a user across all tiers
   (right-to-deletion; called by the delivery layer on account deletion).

## 8. Module layout

```
core/memory/
  ARCHITECTURE.md   ← this document
  manager.py        ← MemoryPort implementer; policy + budget; the only door
  embeddings.py     ← fastembed nomic-embed-text-v1.5 wrapper (lazy singleton)
  store.py          ← Qdrant access; the ONLY module that builds queries;
                      owns collections, payload indexes, user_id filters
```

Config via env: `QDRANT_URL` (default `http://localhost:6333`),
`VRAKSHA_MEMORY_DISABLED=1` forces the degraded mode (tests, CI).

## 9. What stays out (for now)

The background memory-agent (LLM-curated consolidation), Lagrangian weights
learned per user, R2-backed wiki files, and plan-tier enforcement at this
layer (the delivery layer gates tiers today via `allowed_tiers`). Each slots
behind the existing door without contract changes.
