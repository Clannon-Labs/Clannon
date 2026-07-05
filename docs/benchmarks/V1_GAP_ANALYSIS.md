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
| CB2 | Large repository understanding | **ABSENT** | — | high | **yes** |
| CB3 | Unified multi-modal representation | **ABSENT** (string-survival only) | — | high | **yes** |
| CB4 | Institutional decision memory | **PARTIAL** | ★ 3rd | medium (audit mirror) | no |
| CB5 | Security validation | **PARTIAL (near-pass)** | ★ 1st | low | no |
| CB6 | Multi-agent architectural consistency | **PARTIAL (mechanism live)** | ★ 4th | low | no |
| EB1 | Knowledge evolution (temporal truth) | **PARTIAL** | rides CB1 | low | no |
| EB2 | Autonomous project continuity | **PARTIAL** | rides CB1+CB4 | medium | no |
| EB3 | Cross-media knowledge synthesis | **ABSENT** | — | high | **yes** |

Outreach gate = all 6 Critical PASS + ≥1 Exceptional PASS. Today: **0 Critical
PASS, 4 PARTIAL, 2 ABSENT.** The three ABSENT benchmarks (CB2/CB3/EB3) all block
on the same missing subsystem — the Kuzu knowledge-web (PROPOSED — docs/ARCHITECTURE.md §5.2) — so the Critical set cannot fully pass without a graph pass. The
four PARTIAL benchmarks are advanceable now, no graph, and two of them (CB1, CB4)
unlock two Exceptionals (EB1, EB2).

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

### CB2 — Large Repository Understanding — ABSENT
**No harness** (`run_all.py:134` registers it NOT-MEASURED), no dependency-graph,
no traversal capability. This is precisely the Kuzu knowledge-web's reason to
exist (the knowledge-web, PROPOSED — docs/ARCHITECTURE.md §5.2). Answering "what breaks if X is removed /
transitive deps" without full-context ingestion **requires graph traversal**.
**Path:** the graph-web — big structural, **propose-first** per mission. A *thin
credible slice* that could pass a minimal CB2 without full Kuzu: a code-only
static import/dependency graph over the repo (the same shape `check_invariants.py`
already walks) answering "depends-on / breaks-if-removed." Spec it; don't rush it.

### CB3 — Unified Multi-Modal Representation — ABSENT (string-survival only)
**BUILT:** intake→sanitizer→normalizer preprocesses every modality; the media
expert reads image/audio/video/PDF. `tests/benchmarks/c3_multimodal.py` proves a
shared entity **string** survives normalization across modalities.
**ABSENT:** shared **entities**, cross-media **relationships**, **contradiction
detection**, unified knowledge — string-survival is not knowledge. All need the
graph. **Path:** graph-web (same dependency as CB2). Defer.

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
- **EB3 Cross-Media Synthesis — ABSENT.** Needs the graph (rides CB3). Defer.

---

## Priority order (closest-to-pass × highest-leverage)

1. **CB5** — near-pass, lowest cost: surface classify/explain + close the detect
   residual. (Phase 1/3 + capability test.)
2. **CB1** — strong PARTIAL: additive fact/assumption + temporal typing + surfaced
   provenance. **Also unlocks EB1.** (Phase 5.)
3. **CB4** — durable decision-log audit mirror. **Also serves CB6 + EB2 + the
   frontend story.** Propose-first. (Phase 5.)
4. **CB6** — Integration Contract + a real contract-drift test. **This pass.**
5. **CB2 / CB3 / EB3** — all block on the Kuzu knowledge-web. **Propose-first;
   write a build spec; defer to a dedicated graph pass.** Do NOT half-build it.

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

- **CB2 (ABSENT → build via an engineering batch).** Instead of a bare Kuzu web,
  CB2 becomes a batch: engineering expert(s) + heavy deterministic tools (AST-aware
  search, dependency-graph traversal, precise patch-apply) that **navigate** a repo
  larger than any context window rather than ingest it. The graph is still the
  substrate for dependency traversal, but the *capability shape* is now an
  expert-drives-tools batch, not a raw graph query. Still propose-first + big.
- **CB3 / EB3 (ABSENT → media batch over the shared graph).** Unchanged dependency
  on the knowledge-web for shared entities/relationships; the batch layer supplies
  the coordinating media batch once the graph exists.
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
