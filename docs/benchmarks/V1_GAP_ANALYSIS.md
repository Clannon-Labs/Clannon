# V1 Attention-Threshold — Gap Analysis

> **Authority:** diagnosis artifact for the Backend Premium-Parity + V1 Capability
> mission (`docs/benchmarks/mission/`). Measures the current codebase against
> `CLANNON_V1_ATTENTION_THRESHOLD.md` (6 Critical + 3 Exceptional benchmarks).
> **Rule honored:** honest BUILT/PARTIAL/ABSENT per benchmark with `file:line`;
> a truthful "ABSENT, here's the path" beats optimistic prose.
> **Date:** 2026-07-04. **Verdicts trace real code paths + the existing
> `backend/tests/benchmarks/` harnesses**, not docstrings.

---

## Verdict table

| # | Benchmark | Verdict | Closest-to-pass? | Structural cost | Needs graph? |
|---|---|---|---|---|---|
| CB1 | Persistent cross-session memory | **PARTIAL (strong)** | ★ 2nd | low (additive typing) | no |
| CB2 | Large repository understanding | **PARTIAL** (file-level + cross-batch proven; symbol tier absent) | — | medium (symbol tier) | no — built |
| CB3 | Unified multi-modal representation | **PARTIAL** (string-survival + graph-convergence mechanism proven; real media ingestion absent) | — | medium (media extractor) | no — built |
| CB4 | Institutional decision memory | **PARTIAL** | ★ 3rd | medium (audit mirror) | no |
| CB5 | Security validation | **PARTIAL (near-pass)** | ★ 1st | low | no |
| CB6 | Multi-agent architectural consistency | **PARTIAL (mechanism live)** | ★ 4th | low | no |
| EB1 | Knowledge evolution (temporal truth) | **PARTIAL** | rides CB1 | low | no |
| EB2 | Autonomous project continuity | **PARTIAL** | rides CB1+CB4 | medium | no |
| EB3 | Cross-media knowledge synthesis | **PARTIAL** (entity-mediated link proven; direct edge is a schema gap, semantics absent) | — | medium | no — built |

Outreach gate = all 6 Critical PASS + ≥1 Exceptional PASS. Today: **0 Critical
PASS, 6 PARTIAL, 0 ABSENT.** **Updated 2026-07-25:** the Kuzu knowledge-web that
CB2/CB3/EB3 blocked on (ratified 2026-07-06, built + benchmark-proven through
2026-07-25 — `tests/benchmarks/c2_repo_intelligence.py`,
`c3_knowledge_web_convergence.py`, `eb3_cross_media_synthesis.py`) moved all
three from ABSENT to PARTIAL, "Needs graph?" from yes to built. Their remaining
gaps are now CROSS-TREE dependencies (the code-symbol tier and the media
extractor, §3.3/§3.4 of the ratified design), not a graph-substrate gap — see
their detail sections below. The closest-to-pass ranking (★) and priority-order
guidance predate this update and describe the four benchmarks that never
depended on the graph.

---

## Per-benchmark detail

### CB1 — Persistent Cross-Session Memory — PARTIAL (strong)
**BUILT:** 4-tier Qdrant memory with a single write door
(`core/memory/manager.py::record_write_proposals`) and cross-session retrieval
(`::hydrate`), `user_id`-scoped (`core/memory/store.py::_user_filter`), trust
ordering (SEMANTIC>EPISODIC/PROCEDURAL, `_TIER_TRUST`), recency decay, relevance
floor. `tests/benchmarks/c1_memory.py` + `c1_persistent_memory_demo.py` prove the
Day-1-seed → **fresh-session, empty-transcript** Day-7 retrieval, tier survival,
and off-topic distractor drop — the "second-session magic," no chat replay.
**PARTIAL:** the harness itself marks **explain-reasoning** and
**current-vs-historical** as PARTIAL (`c1_memory.py:355,392`). Provenance is
mostly there (`MemoryItem` carries `store/trust/created_at`,
`foundation/contracts/memory.py:27-36`), but there is **no fact-vs-assumption
typing** and **no temporal-validity (`valid_at`)** on the write path, so the two
weakest pass-requirements can't be met.
**Path to PASS (no graph):** additive fields on `MemoryWriteProposal`/`MemoryItem`
— `kind: fact|assumption`, `valid_at`, `superseded_by` — per the already-designed
additive contract (`docs/architecture/memory/ROBUST_MEMORY_ARCHITECTURE.md §7.4`),
plus surface the retrieval "why" (score+tier already computed). **Highest-leverage
non-graph win; also unlocks EB1.**

### CB2 — Large Repository Understanding — PARTIAL (updated 2026-07-25)
**BUILT:** the Kuzu knowledge-web substrate (ratified 2026-07-06, built through
2026-07-25 — `GraphPort`/`GraphManager`/Kuzu behind the port; the "graph DB
choice" half of ADR 0005 is resolved per its own status note). `tests/
benchmarks/c2_repo_intelligence.py` proves the thin-slice file-level graph
(`depends_on`/`breaks_if_removed`/`dependents_of` over Clannon's own real
`backend/` tree — the `_traverse` exponential-blowup/crash bug that used to
hang this exact query is fixed, 2026-07-25) AND the cross-batch `DERIVED_FROM`
claim: two synthetic TASK nodes (standing in for two different batches) each
get their own graph node, both landing in ONE shared graph, each still
traceable back to its origin task — the half of "CB2 (full)" that does not
need the code-symbol tier.
**PARTIAL:** symbol-granularity traversal (function/struct-level nodes, not
just file-level) needs the code-symbol tier (§3.3 of the ratified knowledge-web
design, `proposals/archive/to-backend/2026-07-06_knowledge-web-design-cb2-cb3-eb3.md`)
— a **cross-tree dependency on orchestration's extractor**, not built here.
Natural-language architectural explanations remain NOT-YET (LLM synthesis over
graph results, not the graph substrate's job).
**Path:** no further work needed in `core/memory/` to advance CB2 further — the
graph door is ready and proven; the symbol tier is orchestration's build
whenever they're ready to consume it.

### CB3 — Unified Multi-Modal Representation — PARTIAL (updated 2026-07-25)
**BUILT:** intake→sanitizer→normalizer preprocesses every modality (`tests/
benchmarks/c3_multimodal.py`, shared-entity STRING survival across modalities
— unchanged, still the honest ingestion-precondition proof). ADDITIONALLY, the
knowledge-web substrate is now real: `tests/benchmarks/
c3_knowledge_web_convergence.py` (a companion probe, not an edit to
`c3_multimodal.py` — see that file's own docstring for why) proves the GRAPH
convergence mechanism itself — a real memory-extractor-fed CLAIM and a
hand-seeded MediaSegment (simulating the not-yet-built media extractor) both
converge onto exactly ONE shared ENTITY node (§1.1's canonical-name-identity
rule), read back through the real `GraphPort`, not merely asserted at the unit
level.
**PARTIAL, honestly:** the MediaSegment side is HAND-SEEDED, not produced by a
real ingestion pipeline — automatic PDF/audio/video → entity extraction (§3.4
of the ratified design) does not exist. Every media-worded requirement in the
new harness is capped at PARTIAL, never PASS, for exactly this reason (a
benchmark must never fake a pass). Shared entities/relationships/contradiction
detection/unified knowledge over REAL media remain NOT-YET.
**Path:** §3.4 (the media extractor) is the media pipeline's cross-tree build,
not `core/memory/`'s — the graph door is ready and proven to receive its output
whenever that pipeline exists. No further work needed in `core/memory/` itself.

### CB4 — Institutional Decision Memory — PARTIAL
**BUILT:** `tests/benchmarks/c4_decision_memory.py` ingests the repo's real ADRs
through the write door and retrieves **decision + reasoning + participants** in a
fresh session.
**PARTIAL:** tradeoffs (alternatives+risks) and historical-context ride as **flat
prose in one blob** (`c4_decision_memory.py:634-642`) — not discrete, queryable
records; the debate can't be reconstructed as structured arguments. The **durable
decision-log audit mirror is ABSENT**: `core/orchestrator/utils/decision_log.py`
is in-memory only (streamed over SSE, never persisted) — confirmed no
`audit_mirror`/decision-log persistence anywhere.
**Path (no graph):** build the durable decision-log audit mirror — persist the
in-run decision log as structured records (decision, reasoning, tradeoffs,
participants, ts). Medium structural, **propose-first** (new persistence surface),
self-contained. **High leverage: also serves CB6 traceability + the frontend's
"what did the agent do" story + EB2.**

### CB5 — Security Validation — PARTIAL (near-pass)
**BUILT:** real intake→sanitizer→verifier gates. `tests/benchmarks/c5_security.py`
runs an adversarial battery (injection, jailbreak, malicious markdown, memory
poisoning, encoded exfil, tool abuse) through the **real** stages and asserts
every attack is **blocked + halted + audited** (`c5_security.py:391-392`).
detect/prevent/audit are strong; sole-broker + `user_id` scoping close the
poisoning/retrieval surface.
**PARTIAL:** **detect** is PARTIAL (one residual payload, `c5_security.py:316`) and
**classify/explain** are coarse — the verifier produces a structured reason but it
isn't surfaced as a first-class classification.
**Path (no graph, lowest cost):** widen battery coverage to close the detect
residual + surface the verifier's classification/explanation as structured output.
**Closest to a real PASS — do first.**

### CB6 — Multi-Agent Architectural Consistency — PARTIAL (mechanism live)
**BUILT:** the cross-agent proposal protocol + auto-wake + this mission's
`INTEGRATION_CONTRACT.md` are a live CB6 instance; `scripts/check_invariants.py`
+ the `architecture-boundary` review agent enforce boundary/import consistency;
`tests/benchmarks/sse_contract_drift.py` is a partial contract-drift guard.
**PARTIAL:** no automated cross-agent shared-shape compatibility test beyond the
SSE scan. **Path:** the Integration Contract (Phase 4) + a drift test that fails
when a frontend-consumed backend shape changes without a contract update. **This
pass makes CB6 real.**

### Exceptionals
- **EB1 Knowledge Evolution — PARTIAL.** `e1_knowledge_evolution.py` probe exists;
  needs the same `valid_at`/temporal typing as CB1. **Rides CB1 — cheapest
  Exceptional to reach.**
- **EB2 Autonomous Project Continuity — PARTIAL.** Rides CB1 (state) + CB4 (audit
  mirror). Reachable once both advance.
- **EB3 Cross-Media Synthesis — PARTIAL (updated 2026-07-25).** `tests/
  benchmarks/eb3_cross_media_synthesis.py` proves an entity-mediated cross-modal
  link (a memory-derived CLAIM and a hand-seeded MediaSegment, both reachable
  via one shared ENTITY) — real, substrate-provable, hermetic. It also surfaces
  a genuine schema-completeness finding, verified empirically against the real
  Kuzu schema (not assumed): neither `CONTRADICTS` (Claim-only by design, per
  the ratified §1.4 table) nor `RelatesTo` (Entity-centric by design) has a
  DIRECT Claim<->MediaSegment pair. A literal direct cross-modal edge needs a
  schema decision (flagged to backend) layered on top of §3.4 (the media
  extractor, cross-tree). Rides CB3's substrate.

---

## Priority order (closest-to-pass × highest-leverage)

1. **CB5** — near-pass, lowest cost: surface classify/explain + close the detect
   residual. (Phase 1/3 + capability test.)
2. **CB1** — strong PARTIAL: additive fact/assumption + temporal typing + surfaced
   provenance. **Also unlocks EB1.** (Phase 5.)
3. **CB4** — durable decision-log audit mirror. **Also serves CB6 + EB2 + the
   frontend story.** Propose-first. (Phase 5.)
4. **CB6** — Integration Contract + a real contract-drift test. **This pass.**
5. **CB2 / CB3 / EB3 — updated 2026-07-25.** The Kuzu knowledge-web they
   blocked on is built + benchmark-proven (see their detail sections above).
   Remaining work is now a **cross-tree dependency**, not a memory-specialist
   graph-substrate gap: CB2's symbol tier is orchestration's build (§3.3);
   CB3/EB3's real media ingestion is the media pipeline's (§3.4); EB3's
   direct-edge schema question is a backend/schema decision. No further
   graph-substrate work advances these three further on its own.

**Immediate implementation work** (Phase 1/3, safe, self-contained, serves the
top priorities): (a) memory **persisted-only** surfacing — the Manager returns
what it actually persisted, so `run.memory_writes` never shows a phantom (CB1
honesty); (b) **earn the seal** — expose the filter's real groundedness verdict
(CB5 visibility). Both are additive/reductive, no security-invariant risk, and
directly feed the frontend's honesty story.

---

## How the Batch Architecture changes these paths

The `[PROPOSED]` **Batch Architecture** (`docs/architecture/BATCH_ARCHITECTURE.md`,
owner-authored 2026-07-04) is largely *how* the graph-blocked benchmarks get built,
and it reframes the priority tail — but changes **nothing** about the near-term
non-graph wins above (CB5/CB1/CB4 advance the same way regardless).

- **CB2 (PARTIAL, graph substrate built → full pass via an engineering batch).**
  Instead of a bare Kuzu web, CB2 becomes a batch: engineering expert(s) + heavy
  deterministic tools (AST-aware search, dependency-graph traversal, precise
  patch-apply) that **navigate** a repo larger than any context window rather
  than ingest it. The graph substrate now exists and is benchmark-proven for
  dependency traversal (see CB2's detail section above); the *capability shape*
  for the full pass is still an expert-drives-tools batch, not a raw graph
  query. Still propose-first + big.
- **CB3 / EB3 (PARTIAL, graph substrate built → media batch over the shared
  graph).** The knowledge-web dependency for shared entities/relationships is
  now satisfied (see both benchmarks' detail sections above); what remains is
  the media EXTRACTION pipeline (§3.4) itself — the batch layer supplies the
  coordinating media batch once that pipeline exists.
- **CB6 (PARTIAL → strengthened).** Batches must stay contract-compatible with each
  other and the central orchestrator — the same Integration-Contract discipline,
  applied *internally between batches*. This makes CB6 a live, ongoing test of the
  batch layer, not just the frontend/backend seam.
- **CB1 / EB2 (PARTIAL → prerequisite for the whole thing).** The persistence +
  compaction that let a weeks-long batch-coordinated mission survive session
  restarts *are* CB1/EB2 — so advancing CB1 now (fact/assumption + temporal typing)
  is also foundational for the batch architecture, not just its own benchmark.

**Sequencing:** the batch layer does not jump the queue. It is gated by (0) a
stability audit of the foundations it sits on, (1) the Mission Engine (#5), and (2)
the cross-batch memory contract — all propose-first. Near-term work stays: CB5 →
CB1 → CB4, each of which also *feeds* the batch architecture when it is eventually
built. See `docs/architecture/BATCH_ARCHITECTURE.md` §8 for the build sequence.
