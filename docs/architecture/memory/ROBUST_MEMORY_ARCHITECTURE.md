# Robust Memory Architecture (Target Design)

> **Purpose:** The single proposed target for Clannon's memory layer — the most
> robust design we can justify, synthesised from the 2026 frontier and mapped onto
> Clannon's existing skeleton, invariants, and the Attention Threshold pillars.
> This is the *destination*; it does not replace what is shipped today.
> **Scope:** Knowledge typing, the temporal knowledge graph, hybrid retrieval, the
> governance/curation subsystem (write-gate, consolidation, forgetting,
> reconciliation), and memory-layer security. Everything stays behind the
> `MemoryPort`.
> **Authority level:** Tier 5 (Subsystem), **Status: PROPOSED TARGET.** Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and
> [../../vision/INVARIANTS.md](../../vision/INVARIANTS.md). Where this conflicts
> with the shipped design, the shipped design
> ([backend/core/memory/ARCHITECTURE.md](../../../backend/core/memory/ARCHITECTURE.md))
> is what runs; this is the roadmap. A change here is ratified by an ADR before it
> binds (founder owns memory policy — Attention Threshold §"Founder Responsibility").
> **Related:** [README.md](README.md) (entry point) ·
> [backend/core/memory/ARCHITECTURE.md](../../../backend/core/memory/ARCHITECTURE.md)
> (current shipped) · [../knowledge_graph/README.md](../knowledge_graph/README.md)
> (Pillar 2 home) · [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md) ·
> [../../decisions/proposed/0005-cross-media-knowledge-graph.md](../../decisions/proposed/0005-cross-media-knowledge-graph.md)

---

## 0. The honest claim

"A memory system that doesn't exist on the planet" is real, but precisely scoped.
Every *mechanism* below ships somewhere in 2026:

- the **bi-temporal knowledge graph** is Zep / Graphiti ([arXiv 2501.13956](https://arxiv.org/abs/2501.13956));
- the **governance / belief-revision** layer is SSGM ([arXiv 2603.11768](https://arxiv.org/abs/2603.11768));
- the **self-evolving atomic notes** are A-Mem ([arXiv 2502.12110](https://arxiv.org/abs/2502.12110));
- the **multi-signal retrieval fusion + async writes** are Mem0's 2026 recommendations ([State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026));
- **biologically-inspired forgetting** is FadeMem / LightMem.

What does **not** exist anywhere is the *fusion*: a memory layer that is at once
**(a)** typed as institutional memory (decisions/contracts/risks first, not chat),
**(b)** a bi-temporal cross-media knowledge graph, **(c)** governed by a
belief-revision write-gate with drift-bounded reconciliation, **(d)** carrying
full claim→source provenance lineage, **(e)** hardened against memory poisoning,
and **(f)** hard-isolated per tenant — all behind **one port** that **degrades,
never fails a run**, and is aimed at one job: the freelancer/agency research
workflow that gets smarter every session. The moat is the synthesis and the
target, not a new primitive. Treat every claim below as defensible engineering,
not a benchmark we have already won.

---

## 1. TL;DR — five upgrades to a sound skeleton

Clannon's memory is **not broken**; it is a clean, correct, *flat* baseline (four
Qdrant tiers, `user_id`-scoped, trust-ordered, Lagrangian-budgeted, fail-closed,
degrade-never-fail). The robust design keeps that skeleton and the single door and
upgrades five things, each closing a confirmed weakness from
[`CLANNON_PHASE2_REPORT.md` Part C](../../../drafts/CLANNON_PHASE2_REPORT.md) and a
named 2026 frontier gap:

| # | Upgrade | Kills (Clannon weakness) | Closes (2026 gap) |
|---|---|---|---|
| **L1** | **Typed knowledge** — every memory carries a type from the §I.3 ontology; promotion priority Decision>Contract>Risk>Finding>Conversation becomes a ranking signal | "blob" memory; chat outranking decisions | application memory that can't tell institutional knowledge from chatter |
| **L2** | **Bi-temporal knowledge graph** — semantic + cross-media become entities/edges with validity windows; contradictions invalidate, never silently overwrite | no graph; no conflict resolution (both returned); thin provenance | **staleness** (confidently-wrong facts); **change-as-replacement** instead of transition |
| **L3** | **Hybrid multi-signal retrieval + rerank** — vector + BM25 + graph-BFS, RRF-fused, cross-encoder reranked, MMR-diversified, relevance-floored, with community summaries for global queries | flat top-8, no floor, no rerank, single-shot query embed | **recall collapse at scale**; temporal abstraction at 10× scale |
| **L4** | **The Memory Curator** — governed write-gate (contradiction check), offline consolidation (episodic→semantic gist), Weibull forgetting, mutable-graph↔immutable-ledger reconciliation | unbounded episodic growth; no curation/TTL; no belief revision | **semantic drift**; staleness; unbounded cost |
| **L5** | **Mnemonic sovereignty** — provenance/actor attribution, poisoning quarantine, core-fact contradiction protection on top of existing tenant isolation | memory writes from external content trusted blindly | **memory is the 2026 attack surface** (MINJA / PoisonedRAG / MemoryGraft) |

Everything below preserves the invariants in §4 and lives behind the existing
`MemoryPort` (§7). Nothing here requires the orchestrator to import memory
internals.

---

## 2. Where we are vs the frontier (grounded)

Current shipped behaviour, cited to the code, against the 2026 state of the art.

| Dimension | Clannon today (`core/memory/`) | 2026 SOTA | Verdict |
|---|---|---|---|
| Tiers | 4 flat vector tiers, trust-ordered (`manager.py:29-34`) | typed + episodic/semantic/community subgraphs (Zep) | sound base, flat |
| Retrieval `k` | `MEMORY_SEARCH_TOP_K=10`/tier, single source of truth (dead constant retired) — **Phase 0 ✅** | adaptive k + rerank | partial |
| Relevance floor | `MEMORY_RELEVANCE_FLOOR=0.30` on raw cosine before ranking — **Phase 0 ✅** | floor + rerank + MMR | partial |
| Query | **single-shot** embed of raw request, truncated 2000 ch (`manager.py:83`) | query rewrite/decompose, HyDE, multi-hop | **gap** |
| Lexical/graph signal | vector-only for inferred tiers; wiki is lexical only (`manager.py:151`) | fused vector + BM25 + graph (RRF) | **gap** |
| Temporality | recency *down-weight* only (30-day half-life, floor 0.5 — `manager.py:44-55`); facts never expire | bi-temporal validity windows; edge invalidation (Zep) | **gap** |
| Conflict | both returned; wiki placed higher (`manager.py:142`); **nothing resolves contradiction** | NLI write-gate + edge invalidation (SSGM/Zep) | **gap** |
| Write policy | confidence ≥0.6 (sem/proc) + 0.97 dedup (`manager.py:46-47,184,198`) | governed: contradiction check vs core facts | partial |
| Pruning | **NONE** — episodic grows unbounded (Phase 2 §C) | Weibull decay + budget-aware eviction (FadeMem/SSGM) | **gap** |
| Provenance | item now carries `created_at` ("learned when"), surfaced in the prompt — **Phase 0 ✅**; still missing type/valid_at/source/actor | full lineage: type, valid_at, source episode, actor | partial |
| Typing | untyped strings | typed ontology (forbidden: "blob") — **our own §I.3** | **gap vs our own invariant** |
| Token accounting | real `tiktoken` (cl100k_base) with char fallback — **Phase 0 ✅** | real tokenizer | done |
| Tenant isolation | `user_id` payload filter + `is_tenant` index + defense-in-depth re-verify (`store.py:114-156,217-222`) | most products have *none* | **we lead** |
| Failure model | every fault degrades; 30s breaker (`store.py:35,64-67`) | rarely this disciplined | **we lead** |

Read this as: the **plumbing and the security posture are ahead of the market;
the intelligence of the memory is behind the frontier.** The robust design spends
its effort on the second half without touching the first.

---

## 3. The named 2026 gaps this design targets

From the frontier survey (Mem0 "State of 2026", SSGM, the LongMemEval/LoCoMo/BEAM
literature). These are the problems the *whole field* lists as unsolved — closing
even three of them well is a genuine edge.

1. **Memory staleness** — "accurate until they change jobs, at which point it
   becomes confidently wrong." → **L2** validity windows + **L4** forget gate.
2. **Change as transition, not replacement** — "a user who moves NYC→SF should
   have the *transition* understood, not just the new city stored." → **L2** edge
   invalidation keeps both states with a boundary.
3. **Temporal abstraction at scale** — ~25% accuracy loss from 1M→10M tokens;
   temporal queries are the hardest category. → **L3** community/RAPTOR summaries +
   graph-BFS.
4. **Provenance lineage** — "No tool tracks where the data underlying a stored
   memory came from, through what transformations, or how fresh it is." → **L2/L5**
   episodic-edge lineage + actor attribution. *This is the largest open gap and our
   sharpest differentiator.*
5. **Semantic drift** — repeated summarisation distorts ground truth. → **L4**
   immutable-ledger reconciliation (drift bounded O(N·ε), not O(T·ε)).
6. **Memory poisoning** — "memory became the attack surface" (May 2026). → **L5**
   quarantine + core-fact contradiction protection.
7. **Privacy/consent + deletion** — no standard. → we already have `delete_user`
   right-to-erasure (`store.py:225`); **L5** formalises retention/ACL.

---

## 4. Non-negotiables preserved (the design is invariant-safe)

Every invariant below holds *unchanged*. This is the constraint the design is
solved under, not an aspiration.

| Invariant | How the target honours it |
|---|---|
| §I.4 **Wiki beats everything** | Wiki stays trust=3, carved first in the budget; in the graph it is a *protected core-fact* source that the write-gate (L4) defends against contradiction. |
| §I.5 **Episodic is the baseline** | Episodic becomes the **immutable ground-truth ledger** (L4 dual-track) — even more central, available on every plan. |
| §I.6 **Experts never write directly** | Unchanged. Everything still goes through `record_write_proposals` / `learn`; the Curator is *inside* the door. |
| §I.7 / §V.20 **Only the MemoryPort; one Qdrant, `user_id`-scoped** | All five layers sit behind `manager.py`; `store.py` stays the only query-builder; every new structure (edges, communities, graph) carries `user_id` and is scoped identically. A graph DB, if adopted, is scoped the same way behind the same door. |
| §I.2/§I.3 **Typed, institution-first** | L1 *implements* these (today they are invariants with no mechanism). |
| §VI.25/26 **Media becomes knowledge; raw assets forever** | L2 *is* the cross-media graph home (Pillar 2); raw assets stay in the ArtifactStore, representations regenerate. |
| **Degrade, never fail** | Every new component is best-effort and off the hot path; graph/rerank/curator down ⇒ fall back to today's flat vector hydration with an honest `degraded` note. |

---

## 5. The architecture — five layers behind one door

```
                       ┌──────────────── MemoryPort (unchanged surface) ────────────────┐
  orchestrator ───────▶│ hydrate()  record_write_proposals()  learn()                   │
                       └───────────────────────────┬───────────────────────────────────┘
                                                    │  (all of the below is "inside the door")
   L5 Security / sovereignty ......... actor attribution · poisoning quarantine · ACL+freshness gate · tenant re-verify
   L4 Curator (governance) .......... write-gate (contradiction) · consolidation (sleep-time) · Weibull forget · reconciliation
   L3 Retrieval ..................... query rewrite · vector+BM25+graph-BFS → RRF → cross-encoder rerank → MMR → floor → Lagrangian budget
   L2 Temporal knowledge graph ...... entities · edges(valid/ingest windows) · episodic↔semantic↔community subgraphs · convergence
   L1 Typed knowledge model ......... type ontology · promotion priority · atomic notes (content/keywords/tags/links)
   L0 Substrate ..................... Qdrant (vectors, user_id is_tenant) [+ graph index] · immutable episodic ledger
```

### L0 — Substrate & identity (mostly already built)

Keep the single Qdrant instance, one collection per tier, `user_id` payload
filter with `is_tenant=true` (`store.py:82-89`), and identity-set-once
(`ARCHITECTURE.md §1`). Add two things:

- **An immutable episodic ledger.** Episodic becomes append-only ground truth
  (raw turn episodes with full `trace_id`/`session_id`). Nothing rewrites it; the
  Curator reads it to reconcile the mutable layers (L4). This is SSGM's
  dual-track storage and it is what makes drift *bounded* rather than cumulative.
- **A graph index** (see open decision §10): either Qdrant-native (entities as
  points, edges as a dedicated `vraksha_edges` collection with `user_id` +
  `src`/`dst` payload, adjacency by filtered query) or an embedded graph DB
  (Kuzu) behind the same door. **Recommendation: start Qdrant-native** to avoid a
  new datastore before there is data to justify it (Attention Threshold
  "demonstration first"); graduate to a real graph engine when multi-hop latency
  demands it. Bi-temporal fields live in payload either way, so the migration is
  additive.

### L1 — Typed knowledge model (kills the "blob")

Today a memory is an untyped string — which **violates our own Invariant §I.3.**
The robust model gives every memory a **type** and a **promotion priority**:

- **Type ontology (§I.3):** `Fact · Claim · Assumption · Decision · Risk ·
  Preference · Procedure · Event · Contract · Entity · Relationship`. "Unstructured
  blob" is forbidden.
- **Promotion priority (§I.2):** `Decision > Contract > Risk > Finding >
  Conversation`. This becomes a **ranking multiplier** at hydration, not just a
  tier label — a Decision outranks a Conversation of equal cosine score. This is
  the mechanism Pillar 1 ("decision retrieval outranks conversation retrieval")
  has been missing.
- **Atomic notes (A-Mem):** the writer (`writer.py`) distils each turn into atomic
  typed notes carrying `content, type, keywords, tags, context, embedding, links,
  confidence, source, valid_at`. Notes **link** to related notes; new notes can
  trigger updates to neighbours (A-Mem "memory evolution"), executed by the
  Curator (L4) off the hot path.

The Attention Threshold's **Decision artifact** (`Decision · Reasoning ·
Alternatives · Risks · Evidence · Timestamp · Participants`) is just a `Decision`
note with structured fields — first-class, retrievable, and the highest promotion
priority. This is Pillar 1 made real.

### L2 — The bi-temporal knowledge graph (Zep/Graphiti, and Pillar 2's home)

The semantic tier and the cross-media graph (today: nothing built —
[knowledge_graph/README](../knowledge_graph/README.md) is PROPOSED) become **one
bi-temporal knowledge graph**, scoped by `user_id` like everything else.

- **Three subgraphs** (Zep): the **episodic** ledger (L0, raw episodes), the
  **semantic** subgraph (entities + relationship/claim edges extracted from
  episodes), and a **community** subgraph (clusters of densely-connected entities
  with LLM summaries, for global queries). Episodic edges link every derived fact
  back to the source episode → **provenance lineage for free** (gap #4).
- **Bi-temporal model** (the key idea): every edge carries **two** timelines —
  *event time* `(valid_at, invalid_at)` = when the fact was true in reality, and
  *ingestion time* `(created_at, expired_at)` = when the system learned/retired it.
  This is what closes staleness (gap #1) and change-as-transition (gap #2): when a
  client's status changes, you do **not** overwrite — you set the old edge's
  `invalid_at` to the new edge's `valid_at`. "What is true now" and "what was true
  in March" are both answerable, and nothing is lost.
- **Edge invalidation on contradiction** (Zep): on a new edge, the system compares
  it to semantically-related existing edges; a temporally-overlapping contradiction
  invalidates the older edge (sets `invalid_at`) rather than deleting it. This is
  belief revision, and it is the L4 write-gate's job.
- **Entity convergence (Pillar 2):** the same entity mentioned in a PDF, a diagram,
  and an audio file resolves to **one node** — extraction → embed (cosine
  candidates) + BM25 (name/alias candidates) → LLM resolve against context. This
  is exactly Invariant §VI.25 ("media becomes knowledge; text is a view") given a
  store. Raw assets stay in the ArtifactStore (§VI.26); the graph holds
  representations that can be regenerated.

### L3 — Retrieval: hybrid, reranked, provenance-rich

Replace flat top-8 with a real pipeline. Each stage maps to a failure mode.

1. **Query understanding.** A vague request ("continue the Acme project") is
   decomposed/expanded before retrieval: anchor-entity extraction + optional
   HyDE (embed a hypothetical answer). Fixes the "single-shot embed of the raw
   request" gap (`manager.py:83`).
2. **Multi-signal candidate generation** (Mem0/Zep), run concurrently per the
   existing thread-fan-out (`manager.py:96-99`):
   - **vector** cosine (today's path),
   - **BM25 / lexical** over content + keywords + entity names (today only wiki is
     lexical),
   - **graph-BFS** n-hop from anchor entities (multi-hop reasoning today is
     impossible).
3. **Fusion — Reciprocal Rank Fusion:** `score(d) = Σ_signals 1/(k + rank_s(d))`
   into one normalised score. Cheap, no model call, robust across signals.
4. **Rerank** the fused top-N with a cross-encoder (or a cheap LLM scorer on the
   routing chain). **The relevance floor lives here** — drop anything below
   `θ_rel`. Fixes "returns 8 even if all weak" (`store.py:131-138`).
5. **MMR diversity** (`λ`) so near-duplicates don't crowd the budget — the
   complement to the 0.97 write-dedup.
6. **Promotion-priority + recency + trust + freshness** weighting: final rank =
   `f(rerank_score, type_priority, recency_decay, tier_trust, freshness)`. Stale
   edges (`invalid_at < now`, or Weibull weight `< θ_fresh`) are demoted/excluded
   unless the query is explicitly historical.
7. **Lagrangian budget** (keep the existing water-filling, `manager.py:119-140`)
   over the reranked, floored set — but with a **real tokenizer** (`tiktoken`),
   retiring the `len//4` heuristic and the dead `MEMORY_SEARCH_TOP_K`.
8. **Community/global path** for "what's the overall state of X" — answer from
   community summaries instead of stuffing raw episodes (gap #3; RAPTOR/GraphRAG).

Each returned `MemoryItem` now carries **provenance**: `type, valid_at, created_at,
source (episode/session/trace), actor, confidence` — not just `(store, trust,
score)`. The orchestrator can finally say "learned on date X from task Y," which is
gap #4 and the second-session demo.

### L4 — The Memory Curator (the unbuilt subsystem, finally specified)

This is the designed-but-unbuilt Memory Curator
(`EXPERTS_AND_TOOLS.md:52-53`), specified as **three operators behind the door**,
all best-effort and off the hot path (extending today's `learn()` —
`manager.py:216-230`):

1. **Write-gate (SSGM Truth-Maintenance, runs at write time).** Before a
   `Decision/Contract/Fact/Claim` write commits, run an NLI/LLM contradiction
   check against the user's **protected core facts** (wiki + high-confidence
   decisions). Outcomes:
   - *consistent* → insert (today's path);
   - *near-duplicate* (≥0.97) → refresh/corroborate, **raise confidence** (multiple
     independent sources → Bayesian-style reinforcement) — richer than today's
     `max()`;
   - *contradiction* → **do not silently overwrite** (today's dedup would). Invalidate
     the old edge with a validity boundary (L2) and record the transition; if the
     new claim is lower-trust than a protected core fact, **quarantine** it (L5)
     instead of letting it win.
2. **Consolidation (sleep-time / offline; LightMem).** A scheduled pass (per user,
   idle or post-session) that: clusters redundant episodics and **gists** them into
   semantic notes (episodic→semantic promotion); builds/refreshes **community
   summaries**; re-links atomic notes (A-Mem evolution); recomputes confidence.
   LightMem reports up to 117× fewer tokens doing this offline vs inline — it is
   both cheaper and sharper. This is also where the Lagrangian *weights* can be
   learned per user (the `ARCHITECTURE.md §9` "out for now" item).
3. **Forget / decay (FadeMem / SSGM Weibull).** Replace "no pruning ever" with
   **active forgetting**: `w(Δτ) = exp(-(Δτ/η)^κ)` on access-recency; demote below
   `θ_fresh`; evict low-value, never-retrieved `Conversation/Event` episodics under
   a per-user cap. **Institutional memory is protected** — `Decision/Contract/Risk`
   and wiki never decay out (Invariant §I.2). This closes unbounded growth (Phase 2
   D3) while keeping the moat.

Underpinning all three: **reconciliation** (SSGM). Periodically replay the mutable
semantic/graph layer against the immutable episodic ledger and correct accumulated
drift. This bounds expected drift at `O(N·ε)` (N = window) instead of `O(T·ε)`
(T = lifetime) — i.e. the store stays *true to what actually happened* no matter
how many times it has been summarised.

### L5 — Mnemonic sovereignty (memory as the attack surface)

Clannon already leads on tenancy (the `user_id` filter is the *only* place a query
is built — `store.py:114-118`; defense-in-depth re-verifies every hit and every
upsert target — `store.py:142-152,217-222`). The robust design adds the *content*
half, because in 2026 "memory became the attack surface" (MINJA ≥95% inject
success; PoisonedRAG ~90% with 5 docs; MemoryGraft implants fake "successful
experiences"):

- **Actor attribution / provenance signing.** Every memory tagged
  `source ∈ {user, agent-inference, external-web, media}`. External-web and
  agent-inference start at **lower trust** and face the harder write-gate. This is
  the lineage gap (#4) doubling as a poisoning defense.
- **Quarantine before influence.** A write derived from external/tool content is
  not trusted until verified — it cannot contradict a core fact or steer future
  turns until the Curator clears it. (Re-entry sanitization already scrubs external
  *content* — Phase 2 integrity note, `handler/tools.py:110-151`; this extends the
  guarantee to *persistence*.)
- **Core-fact contradiction protection.** A low-trust injected memory can never
  silently overwrite a high-trust user fact — the L4 write-gate refuses it. This is
  SSGM's `ΔM ∧ M_core ⊭ ⊥` made concrete and is a direct MINJA/MemoryGraft defense.
- **Read gate.** Retrieval already filters by `user_id`; add the freshness
  predicate (`w(Δτ) ≥ θ_fresh`) so stale/quarantined memory cannot surface. ACLs
  stay per-tenant (we never share memory across users → no topology-induced
  leakage).

Most memory products ship **zero** of this. It is a real differentiator and it
costs little on top of the isolation we already have.

---

## 6. The math levers (failure mode → lever)

In keeping with the math-first stance — *the human contribution is diagnosing which
lever maps to which failure mode* — every robustness property has one explicit,
tunable mechanism:

| Failure mode (observed/anticipated) | Lever | Where |
|---|---|---|
| Right fact outside top-8 as corpus grows | RRF fusion + cross-encoder rerank + MMR(`λ`) | L3 |
| Weak hits fill context | relevance floor `θ_rel` | L3 |
| Vague request retrieves nothing specific | query decomposition + HyDE + graph-BFS anchors | L3 |
| Confidently-wrong stale fact | bi-temporal `(valid_at, invalid_at)` + freshness `w(Δτ)=exp(-(Δτ/η)^κ)` | L2/L4 |
| Contradiction silently overwrites truth | NLI write-gate `ΔM ∧ M_core ⊭ ⊥`; edge invalidation | L4/L2 |
| Summarisation distorts ground truth over time | ledger reconciliation, drift `O(N·ε)` not `O(T·ε)` | L4 |
| Episodic grows unbounded | Weibull decay + budget-aware eviction (institutional protected) | L4 |
| Chat outranks decisions | promotion-priority multiplier (Decision>…>Conversation) | L1/L3 |
| Budget mis-spent across tiers | Lagrangian water-filling (keep), real tokenizer | L3 |
| Confidence is a guess | Bayesian reinforcement on independent corroboration | L4 |
| Same entity fragments across media | cosine+BM25 candidate gen → LLM entity resolution | L2 |
| Injected "memory" steers the agent | actor attribution + quarantine + core-fact protection | L5 |

---

## 7. MemoryPort surface, execution & concurrency model

The `MemoryPort` stays **the only door** (Invariant §I.7). This section pins down
*how* that door executes: what is code vs LLM, what runs when, and who is allowed
to open it. These are decisions, not options — they answer "should the memory
layer be an LLM call or robust code?" precisely, per operation.

### 7.1 The split — reads are code, writes/maintenance are async LLM

The read door is **code-only and never calls a generative LLM.** The only LLM in
the memory layer lives behind the **write/maintain** door, and it **always runs
asynchronously, off the user's turn.** This is already the codebase's instinct —
`hydrate` is deterministic code (`manager.py`), `learn()`/`writer.distill` is the
LLM running best-effort off the hot path (`manager.py:216-230`) — formalised and
extended.

| Operation | Implementation | On the user's turn? | Why |
|---|---|---|---|
| **Hydrate** (proactive read) | **code-only**, deterministic ranking | yes — but runs **∥ the verifier** → ~0 added wait (7.2) | speed; provenance is metadata, not a guess; degrades cleanly |
| **On-demand search** (orchestrator asks the port mid-reason) | **code-only** | yes — fast, non-blocking | same path as hydrate, with a fresh query |
| **Rerank** (L3) | **local cross-encoder** (a model, *not* a generative LLM) | yes — bounded, optional | recall quality without generation cost/RPM |
| **Query rewrite / HyDE** (L3) | **LLM, opt-in** | only on a deliberate *deep* search, **never** on hydration | keeps the parallel hydration path LLM-free |
| **Write / distill** (turn → typed notes) | **LLM** | **NO — async, post-delivery** | extracting typed Decisions/Risks + reasoning is inherently generative |
| **Write-gate** (contradiction / belief revision, L4) | **small NLI model or LLM** | **NO — async** | "does ΔM contradict a core fact" is semantic inference |
| **Maintain — mechanics** (decay, eviction, dedup, validity bookkeeping, L4) | **code-only** | **NO — offline / sleep-time** | deterministic arithmetic |
| **Maintain — semantics** (gist/consolidate, entity resolution, community summaries, reconciliation, L4) | **LLM** | **NO — offline / sleep-time** | generative/semantic |

**Direct answer to "no writer, code-only?":** a memory layer with **no LLM on the
hot path** is exactly right and achievable — that is the read door. A memory layer
with **no LLM at all** is *not* compatible with the benchmark: CB4 (institutional
decision memory) and XB1 (knowledge evolution) require distilling typed decisions
with reasoning and resolving contradictions, which cannot be done deterministically
from free text. So keep the writer — but make it 100% asynchronous and invisible to
the turn's latency. Reads never wait on it.

### 7.2 Concurrency — nothing blocks unless it must

Today hydration is **blocking at orchestrator entry** (`loop.py:80`, awaited before
reasoning) and happens *after* the verifier stage. Target model:

- **Hydration ∥ verification.** Launch hydration as a concurrent task the moment
  **normalization** is done, so it overlaps the verifier LLM call. It is awaited at
  orchestrator entry, where the wait is ≈ 0 because it already ran. *Safety:* the
  read is **read-only and `user_id`-scoped**, so retrieving against not-yet-verified
  input only ever searches the user's *own* memory — no leak, no write. The hydrated
  package is **injected/acted on only if the verifier passes**; if the verifier
  **blocks** the turn, the hydration result is discarded (cheap). This crosses the
  security-stage boundary, so the hydration task must **not mutate Flow** mid-verify —
  its result still enters via the orchestrator's `HydrationPackage` exactly as today,
  just computed earlier (Flow-only transport, §I, preserved).
- **Hydration is never a gate.** If it is somehow not ready at orchestrator entry,
  the orchestrator proceeds with whatever is ready (wiki/episodic are fastest) and
  **back-fills via on-demand search** — it never stalls. (Memory is augmentation,
  not a gate — orchestrator `CLAUDE.md`.)
- **Writes are fire-and-forget.** The orchestrator hands a write intent (or the
  finished turn) to the port and returns immediately; distillation → write-gate →
  persist all run in the background. *Consequence:* **read-your-writes is not
  guaranteed within the same turn** (writes land post-delivery). That is fine — the
  research workflow never needs to read back what it just wrote mid-turn; memory is
  eventually consistent by design.
- **Maintenance is offline.** Consolidation/forgetting/reconciliation run on a
  schedule (idle / post-session / nightly), per user — never on any turn.

Net: on a turn, the only memory work on the critical path is a code-only hydrate
that already overlapped the verifier, plus any code-only on-demand searches. Every
LLM-touching operation is parallel or offline.

### 7.3 Orchestrator is the central authority — push context, broker the rest

The orchestrator becomes the **central reasoner and the sole memory broker**, not
just a tool-driving agent (its role today — orchestrator `CLAUDE.md`).

- **The orchestrator holds the `MemoryPort`; experts do not.** ✅ **BUILT
  (2026-07-03):** no expert holds a `memory.*` grant any more
  (`experts/{writer,documentation,web_research}/expert.py`; invariant locked in
  `tests/orchestrator_memory_broker.py`). Experts must not open the
  memory door themselves — this shrinks the number of surfaces that touch memory
  (better for the single-door rule and `user_id` scoping) and keeps expert context
  controlled.
- **Push, don't pull (primary path).** The orchestrator assembles a **per-expert
  context bundle** — the slice of hydrated/searched memory that expert needs plus
  its task brief — and hands it in at spawn. Experts are *not* stateless and do
  *not* fetch; they receive exactly the context the orchestrator decided they need.
  *Built form (2026-07-03): the whole TURN's hydrated memory is pushed to every
  expert (`ExpertEnv.hydration` → `_memory_note` in `handler/support.py`); the
  per-expert SLICING of that bundle remains open.*
- **Broker, don't open (fallback path).** When an expert discovers mid-task that it
  needs more (a newly-surfaced entity's history), it **asks the orchestrator** (a
  structured "need-context" request in its return channel); the orchestrator runs
  the on-demand search and hands results back. The expert still never touches the
  port. This keeps "orchestrator = central authority" true without starving experts
  that genuinely need to discover.
  *Built form (2026-07-03): the orchestrator brokers recall PRE-SPAWN (prompt
  §"Brokering memory for experts"; it keeps `memory.search` natively). The mid-task
  expert→orchestrator "need-context" channel is NOT built.*
- **Central reasoning, lean context — the tension, resolved.** The existing
  invariant "the orchestrator never receives raw expert output, only brief
  summaries" (orchestrator `CLAUDE.md`) seems to fight "central reasoner." It does
  not: the orchestrator reasons over **summaries + its hydrated memory** by default,
  and when final synthesis genuinely needs an expert's detail it **pulls that one
  full finding on demand** (same broker pattern) — full findings still flow to the
  output pipeline as today. Context stays lean; reasoning stays central.

> Cross-domain note: 7.3 is partly an **orchestrator-domain** change (the reasoning
> loop, expert grants, the per-expert context bundle, the need-context channel).
> This doc is authoritative on the **memory contract** it implies; the orchestrator
> doc/agent owns the loop change. They must land together.

### 7.4 The port surface (additive contract)

`foundation/contracts/memory.py` needs **only additive** changes:

- `MemoryItem` gains optional `type`, `valid_at`, `source`, `confidence`
  (`created_at` already shipped — Phase 0). Defaults preserve old behaviour.
- `MemoryWriteProposal` gains optional `type` and `source` (defaults =
  today's untyped / agent-inference).
- `HydrationRequest` may gain optional `as_of` (for "what did we know in March")
  and `query_hints`.
- **Read methods stay code-only:** `hydrate` (proactive) and an explicit
  first-class **`search(query, …)`** read capability the orchestrator calls on
  demand (today this is the `memory.search` *tool* wrapping `MemorySearcher` →
  `hydrate`; promote it to a named port read so the broker path in 7.3 is clean).
- **Write door stays async:** `record_write_proposals` / `learn` keep their
  signatures and run fire-and-forget; the Curator's consolidation/forget/reconcile
  passes are internal **scheduled** entry points behind the door, not turn-driven
  port methods (`ARCHITECTURE.md §9`).

If a graph DB is adopted, it is constructed only inside `store.py` (or a sibling
`graph.py` obeying the same single-door rule), `user_id`-scoped identically.
Invariant §V.20 holds.

### 7.5 Readiness — the minimal scaffolding to build toward this now

To make the codebase *ready* for the model above without a big-bang refactor:
1. Promote on-demand `search` to a named `MemoryPort` read (wrap today's
   `MemorySearcher`); keep `hydrate` code-only.
2. Add the additive `type`/`source`/`valid_at` fields (7.4) — they unblock L1.
3. Move hydration launch to **post-normalize, concurrent with verify**; await at
   orchestrator entry (a small pipeline/`loop.py` change, Flow-safe per 7.2).
4. Remove `memory.search` from expert grants; add a per-expert **context-bundle**
   input and an expert→orchestrator **need-context** request path (orchestrator
   domain — land with the loop change). ✅ *Grants removed + turn-level context
   push built 2026-07-03 (`ExpertEnv.hydration`); the mid-task need-context
   request path remains open.*
5. Keep `learn()`/distillation async (already is); add the scheduled maintenance
   entry point as a no-op stub the Curator (L4) will fill.

Everything above is degrade-never-fail: any of these down ⇒ fall back to today's
blocking-but-correct hydrate with an honest `degraded` note.

---

## 8. Attention Threshold pillar mapping

The robust memory layer is the backbone of three of the four pillars and the
Outreach Readiness Gate.

| Pillar / Gate | What this design provides |
|---|---|
| **Pillar 1 — Persistent organizational memory** | L1 typed `Decision` notes (Decision/Reasoning/Alternatives/Risks/Evidence/Timestamp/Participants) + promotion-priority retrieval = "a new session reconstructs *why* a decision was made, what alternatives existed, what risks were accepted" without chat history. |
| **Pillar 2 — Cross-media knowledge graph** | L2 *is* the graph home — entity convergence across PDF/image/audio/video/code into one node; this is the missing connective layer ADR 0005 and the [knowledge_graph README](../knowledge_graph/README.md) point to. |
| **Pillar 3 — Repository intelligence** | the same bi-temporal graph holds file/dependency/architectural/decision/ownership edges; L3 graph-BFS + community summaries answer "what breaks if X is removed?" without prompt-stuffing. |
| **Pillar 4 — Agent civilization** | institutional artifacts (RFC/Decision/Objection/…) are typed notes with the highest promotion priority; provenance lineage (L2/L5) is exactly "who decided, why, who objected, what changed" surviving sessions (ADR 0009). |
| **Outreach Gate (≤3-min demo)** | the second-session demo: upload a brief, run a task, start a *new* session, ask "why did we pick vendor X for Acme?" — answered from typed decision memory with date+source provenance and no chat history. That is the capability that makes an engineer recognise this isn't a chat wrapper. |

### Benchmark coverage — `CLANNON_V1_ATTENTION_THRESHOLD.md`

Where memory stands against the V1 bar today, and which layer closes each gap. The
9 benchmarks collapse into the same 5 capabilities (L1–L5). "Memory dimension" only —
CB2/CB6 also need non-memory subsystems (repo ingestion, the agent/contract layer).

| Benchmark | Memory status today | Gap | Closed by |
|---|---|---|---|
| **CB1** Persistent cross-session | **PARTIAL** — retrieval mechanics + `created_at` (Phase 0); no `type`, no validity | can't do "fact vs assumption" or "current vs historical"; `rationale` stored but unsurfaced | **L1 + L2-time** (+ cheap: surface `rationale`/`source`) |
| **CB2** Large repo understanding | **FAIL** — no graph | no dependency/architectural graph, no multi-hop | **L2-graph** + repo-ingestion producer (cross-subsystem) |
| **CB3** Unified multi-modal | **FAIL** — no entity model | no convergence, no cross-media edges, no contradiction detection | **L2-graph + L4** |
| **CB4** Institutional decision memory | **FAIL** — writer emits only semantic/procedural (`writer.py:39-43`) | no `Decision` type; reasoning/participants lost | **L1** (+ L5 for participants) |
| **CB5** Security (memory) | **PARTIAL** — tenancy strong; no poisoning defense | no actor attribution / quarantine / core-fact protection | **L5** |
| **CB6** Multi-agent consistency | **PARTIAL** — mostly agent/contract layer | memory side lacks typed artifacts + attribution | **L1 + L5** (memory contribution) |
| **XB1** Knowledge evolution | **FAIL** — recency down-weight only | no validity windows/transition; contradictions co-surface | **L2-time + L4** |
| **XB2** Autonomous continuity | **PARTIAL** — `created_at` helps "recent" | no `Risk` type; vague-query recall single-shot | **L1 + L3** |
| **XB3** Cross-media synthesis | **FAIL** — no graph | same as CB3 | **L2-graph** |

**By layer (unlock count):** L1 → CB4 + ½CB1 + XB2 (high coverage, low effort). L2
→ CB1(time) + CB2 + CB3 + XB1 + XB3 (highest coverage, highest effort, needs the
graph-store decision). L3 → recall quality for CB1/XB2 + CB2 global. L4 → CB3/XB1
contradiction + CB1 staleness. L5 → CB5 + participants for CB4/CB6.

**Bottleneck:** **L1 + L2-time alone flip CB1, CB4, XB1 to PASS** — two of the five
Demo-Readiness items and the two most "obviously not RAG" moments — *without
building the graph.* The graph (CB2/CB3/XB3) is unavoidable but sequenced last
because it is cross-subsystem. Demo-Readiness latency (90–180s, no manual injection)
is exactly why the execution model in §7 (code-only reads, ∥-verifier hydration,
async writes) is benchmark-driven, not just elegant.

---

## 9. Build path (demonstration-first, cheapest leverage first)

Ordered so each step is independently shippable, demonstrable, and degrades
cleanly. Tracks Phase 2 Part E's cheap-wins/real-builds split.

**Phase 0 — cheap wins (config/wiring, no new subsystem). ✅ SHIPPED 2026-06-17.**
Relevance floor `MEMORY_RELEVANCE_FLOOR=0.30` (`manager.py`, applied on raw cosine
before ranking); retired the dead `MEMORY_SEARCH_TOP_K` (now the single source of
truth for per-tier `k`, replacing the local `_SEARCH_K`); real `tiktoken`
(cl100k_base) token accounting with a char-heuristic fallback; `MemoryItem.created_at`
surfaced and rendered in the orchestrator prompt as a "learned when" hint
(`foundation/contracts/memory.py`, `core/orchestrator/utils/prompt.py`). Tests
green. *Demo:* sharper, provenance-tagged recall today. (Full `source`/actor
attribution is Phase 1/L5 — Phase 0 ships `created_at` only.)

**Phase 1 — typed knowledge + provenance (L1).** Add the type field + promotion
priority + atomic-note distillation in `writer.py`. *Demo:* "decisions outrank
chat" — Pillar 1's retrieval requirement, with no graph yet.

**Phase 2 — hybrid retrieval + rerank (L3).** BM25 + RRF + cross-encoder rerank +
MMR. Biggest single recall win; no new datastore. *Demo:* recall holds as the
corpus grows (the moat's failure mode, fixed).

**Phase 3 — the Curator (L4).** Write-gate (contradiction check), Weibull
forgetting + eviction, offline consolidation. *Demo:* "your store stays lean and
never goes confidently-wrong"; bounded growth.

**Phase 4 — bi-temporal graph + convergence (L2).** Entities/edges with validity
windows, edge invalidation, cross-media entity resolution. Largest build; unlocks
Pillars 2–3. *Demo:* "what was true in March vs now"; multi-hop "what depends on
Y." **This is the step that needs the §10 graph-DB decision.**

**Phase 5 — sovereignty hardening (L5).** Actor attribution, quarantine,
core-fact protection, reconciliation. *Demo:* "we resist memory poisoning" — a
security story no competitor tells.

The order is deliberately **value-before-graph**: Phases 0–3 are pure upside on the
existing vector store and deliver the second-session demo; the graph (Phase 4) is
the heaviest lift and is gated on having data and the datastore decision.

---

## 10. Honest assessment — novelty, risk, open decisions

**What is genuinely new vs synthesis.** No new ML primitive is claimed. The
novelty is (a) the *combination* — typed institutional memory + bi-temporal
cross-media graph + governed belief-revision + provenance lineage + poisoning
defense + hard tenancy, behind one degrade-never-fail port — and (b) the *target*:
none of the named systems aim at the freelancer/agency research workflow with
cross-media and repository intelligence. That is a defensible product moat; it is
not a research breakthrough, and we should not market it as one.

**Risks.**
- *Over-building ahead of demonstrable value.* The graph (Phase 4) is the classic
  trap — it is why the order puts retrieval and the Curator first. Build the
  demonstrable slice first (Attention Threshold rule).
- *Cost/latency of rerank + write-gate.* Both add LLM/model calls; both are gated
  by the dev free-tier Gemini 20-RPM ceiling (paid tier needed for wide
  fan-out). Mitigation: cross-encoder (not LLM) rerank;
  write-gate and consolidation run **offline** (sleep-time), off the hot path.
- *Over-pruning.* Aggressive forgetting can delete something that mattered
  (stability-plasticity). Mitigation: institutional types never decay; the
  immutable ledger means a wrong gist is always recoverable by reconciliation.
- *Drift from a third "authoritative" doc.* This is a *target*, deliberately
  marked PROPOSED; the shipped `backend/core/memory/ARCHITECTURE.md` remains the
  description of what runs. Do not let them blur.

**Decided this revision (§7).**
- **Execution model:** reads = code-only (no generative LLM on the hot path);
  writes + maintenance = LLM-assisted but always async/offline. A no-LLM-at-all
  memory layer is rejected (incompatible with CB4/XB1).
- **Concurrency:** hydration runs ∥ the verifier (post-normalize, gated on
  verifier-pass); on-demand search is code-only/non-blocking; writes are
  fire-and-forget (eventual consistency, no read-your-writes within a turn).
- **Authority:** the orchestrator holds the port and is the central reasoner +
  sole memory broker; experts lose the `memory.search` grant and receive pushed
  context (with an orchestrator-brokered pull fallback).

**Open decisions (need founder sign-off → ADR).**
1. **Graph store.** **Resolved (2026-06-26) → embedded Kuzu** behind a GraphPort, with
   Qdrant retained as the vector layer (entry by similarity → walk the web); Neo4j is a
   future scale-up swap. See [../../ARCHITECTURE.md](../../ARCHITECTURE.md) §5.2. This
   supersedes the prior "Qdrant-native through Phase 3" recommendation and closes the
   open question in ADR 0005.
2. **Orchestrator reasoning shift (cross-domain).** **Resolved → landed 2026-07-03**
   (sole-broker, `ARCHITECTURE.md §7.3`): expert `memory.search` grants removed,
   hydrated context pushed to experts (`ExpertEnv.hydration`), pre-spawn brokered
   recall in the orchestrator prompt. The fuller "central reasoner" elevation
   (per-expert bundles, need-context channel) stays a roadmap item.
3. **Embedding space.** Stay on local nomic-768 (`embeddings.py`) or add a second
   space for entities (Zep uses 1024-d)? Invariant §VI.24 says never trust one
   embedding space — but multi-space is a Phase 4 concern.
4. **Rerank model & routing.** Cross-encoder (local, cheap, fixed) vs LLM scorer
   (better, RPM-bound). Lives in `models.yaml` like every other role.
5. **Eval harness.** None today. Adopt LongMemEval-V2 / LoCoMo-style fixtures
   scoped to our workflow before tuning `θ_rel`, `η`, `κ`, `λ` — "application-level
   evaluation" is itself a named 2026 gap; build the freelancer-workflow eval so we
   tune against reality, not a generic benchmark.

---

## 11. References (2026 frontier)

- Zep / Graphiti — temporal knowledge-graph agent memory, bi-temporal model,
  episodic/semantic/community subgraphs, RRF/MMR/cross-encoder retrieval —
  [arXiv 2501.13956](https://arxiv.org/abs/2501.13956),
  [Neo4j: Graphiti](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/).
- A-Mem — agentic, self-organising Zettelkasten memory; atomic notes + evolution —
  [arXiv 2502.12110](https://arxiv.org/abs/2502.12110).
- SSGM — Stability- and Safety-Governed Memory; write-gate, Weibull forgetting,
  dual-track reconciliation, drift bound, provenance —
  [arXiv 2603.11768](https://arxiv.org/html/2603.11768v1).
- Mem0 — multi-signal retrieval, async writes, actor attribution; 2026 benchmarks
  and production gaps —
  [State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026).
- LightMem — sleep-time/offline consolidation (≈117× token reduction) —
  [arXiv 2510.18866](https://arxiv.org/html/2510.18866v1).
- FadeMem — biologically-inspired active forgetting, dual-layer decay —
  [alphaXiv 2601.18642](https://www.alphaxiv.org/audio/2601.18642).
- RAPTOR / GraphRAG / HippoRAG2 — hierarchical & graph retrieval for global queries.
- Memory-poisoning threat model — MINJA, PoisonedRAG, MemoryGraft; "memory became
  the attack surface" —
  [arXiv 2601.05504](https://arxiv.org/html/2601.05504v2),
  [arXiv 2512.16962](https://arxiv.org/html/2512.16962v1),
  [Survey: Security of Long-Term Memory (Mnemonic Sovereignty)](https://arxiv.org/html/2604.16548v1).
- LongMemEval / LoCoMo / BEAM — the benchmarks to tune against —
  [LongMemEval](https://github.com/xiaowu0162/longmemeval).
