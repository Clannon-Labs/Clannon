# V1 Attention-Threshold — Gap Analysis

> **Authority:** diagnosis artifact for the Backend Premium-Parity + V1 Capability
> mission (`docs/benchmarks/mission/`). Measures the current codebase against
> `CLANNON_V1_ATTENTION_THRESHOLD.md` (6 Critical + 3 Exceptional benchmarks).
> **Rule honored:** honest BUILT/PARTIAL/ABSENT per benchmark with `file:line`;
> a truthful "ABSENT, here's the path" beats optimistic prose.
> **Reconciled:** 2026-07-28. **Verdicts trace real code paths + the existing
> `backend/tests/benchmarks/` harnesses**, not docstrings.

---

## Verdict table

| # | Benchmark | Verdict | Closest-to-pass? | Structural cost | Needs graph? |
|---|---|---|---|---|---|
| CB1 | Persistent cross-session memory | **PARTIAL (strong)** | open | low (explanation + temporal linkage) | no |
| CB2 | Large repository understanding | **PARTIAL** (symbol/AST/dependency/archive tiers built; architectural explanation absent) | open | medium (explanation synthesis) | no — built |
| CB3 | Unified multi-modal representation | **PARTIAL** (string-survival + graph-convergence mechanism proven; real media ingestion absent) | — | medium (media extractor) | no — built |
| CB4 | Institutional decision memory | **PARTIAL** | open | medium (structured tradeoffs/history + complete participants) | no |
| CB5 | Security validation | **PARTIAL (near-pass)** | open | low (detect residual) | no |
| CB6 | Multi-agent architectural consistency | **PASS** | complete | — | no |
| EB1 | Knowledge evolution (temporal truth) | **PARTIAL** | rides CB1 | low | no |
| EB2 | Autonomous project continuity | **PARTIAL** | rides CB1+CB4 | medium | no |
| EB3 | Cross-media knowledge synthesis | **PARTIAL** (entity-mediated link proven; direct edge is a schema gap, semantics absent) | — | medium | no — built |

Outreach gate = all 6 Critical PASS + ≥1 Exceptional PASS. Today: **1 Critical
PASS, 5 PARTIAL, 0 ABSENT.** **Updated 2026-07-25:** the Kuzu knowledge-web that
CB2/CB3/EB3 blocked on (ratified 2026-07-06, built + benchmark-proven through
2026-07-25 — `tests/benchmarks/c2_repo_intelligence.py`,
`c3_knowledge_web_convergence.py`, `eb3_cross_media_synthesis.py`) moved all
three from ABSENT to PARTIAL, "Needs graph?" from yes to built. CB2's symbol
tier has since landed; its architectural-explanation requirement remains
NOT-YET. CB3/EB3 still need real media extraction (§3.4), not more graph
substrate work. **Reconciled 2026-07-28:** CB6 now passes; stale
priority stars were removed because they directed agents toward completed
CB4/CB5/CB6 sub-work rather than remaining benchmark gaps.

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
**PARTIAL:** fact-vs-assumption typing and `valid_at` have landed; the current
harness marks that discriminator PASS. Explain-reasoning and
current-vs-historical remain PARTIAL: score/tier provide a machine-readable
retrieval basis, but no reasoning narrative exists, and supersession is not a
linked temporal relationship. Provenance remains PARTIAL because author/RFC
linkage is incomplete (`tests/benchmarks/c1_memory.py`).
**Path to PASS (no graph):** add retrieval explanation, complete provenance,
and link superseded knowledge so current and historical states are explicit.
This also advances EB1.

### CB2 — Large Repository Understanding — PARTIAL (updated 2026-07-28)
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
The code-symbol tier, AST-aware search, dependency-graph traversal, archive
ingestion, and cross-call workspace persistence have since landed and carry
their own focused tests (`tests/orchestrator_code_symbols.py`,
`tests/orchestrator_archive_extraction.py`, and related workspace/graph tests).
**PARTIAL:** `tests/benchmarks/c2_repo_intelligence.py` still marks
`architectural_explanations` NOT-YET. Deterministic navigation and relationship
results do not yet produce natural-language architectural explanations.
**Path:** exercise the landed tiers in an explanation layer and extend the CB2
acceptance harness. Do not count raw graph results as explanation.

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
**BUILT since original diagnosis:** durable `DecisionRecord` audit mirror plus
owner-scoped `GET /runs/:id/decisions`, including terminal delivered, blocked,
failed, and cancelled paths (`api/run_driver.py`, `api/decision_audit.py`;
`tests/decision_audit.py`, `tests/decision_record.py`).
**PARTIAL:** tradeoffs (alternatives+risks) and historical context still ride as
flat prose rather than discrete, queryable records
(`tests/benchmarks/c4_decision_memory.py`). Crash/cancellation derivation uses
the live log but lacks returned-flow expert/tool context, so some records have
incomplete `participants`. The benchmark's ADR path also still marks
participants NOT-YET.
**Path (no graph):** structure tradeoffs and historical links; preserve complete
participant context on every terminal path; extend the CB4 harness.

### CB5 — Security Validation — PARTIAL (near-pass)
**BUILT:** real intake→sanitizer→verifier gates. `tests/benchmarks/c5_security.py`
runs an adversarial battery (injection, jailbreak, malicious markdown, memory
poisoning, encoded exfil, tool abuse) through the **real** stages and asserts
every attack is **blocked + halted + audited** (`c5_security.py:391-392`).
detect/prevent/audit are strong; sole-broker + `user_id` scoping close the
poisoning/retrieval surface.
**PARTIAL:** **detect** remains PARTIAL: one adversarial payload evades the
deterministic screen, and live semantic detection remains separately certified
rather than hermetically proven (`tests/benchmarks/c5_security.py`). Structured
classification/explanation and earned-seal surfacing have landed.
**Path (no graph):** close the detect residual and widen the proving battery.

### CB6 — Multi-Agent Architectural Consistency — PASS (updated 2026-07-28)
**BUILT:** pull-based proposal workflow, `reports/INTEGRATION_CONTRACT.md`, and
`tests/benchmarks/sse_contract_drift.py`. The harness exercises real backend
mappers, parses frontend TypeScript, compares event/payload/vocabulary shapes,
and fails on material shared-contract drift. `scripts/check_invariants.py` and
architecture-boundary review cover repository boundaries.
**PASS:** shared integration contract exists and automated compatibility
enforcement is green. Future batch seams remain subject to same no-drift rule;
that ongoing obligation does not reduce current benchmark verdict.

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

## Remaining work

CB6 is complete. CB4's durable mirror and CB5's earned-seal surfacing are also
complete sub-work; neither should be advertised as next work.

Open benchmark gaps:

1. **CB3 / EB3:** real media extraction/ingestion; direct-edge semantics still
   need a schema decision.
2. **CB1 / EB1:** retrieval explanation, complete provenance, and explicit
   supersession/temporal linkage.
3. **CB2:** architectural explanation over landed symbol/AST/dependency/archive
   capabilities.
4. **CB4 / EB2:** structured tradeoffs/history and complete crash-path
   participants.
5. **CB5:** deterministic-detect residual.

`docs/ROADMAP.md` remains canonical for cross-role ordering and owner gates.

---

## How the Batch Architecture changes these paths

The `[PROPOSED]` **Batch Architecture** (`docs/architecture/BATCH_ARCHITECTURE.md`,
owner-authored 2026-07-04) is largely *how* the graph-blocked benchmarks get built,
and it reframes the priority tail — but changes **nothing** about the near-term
non-graph wins above (CB5/CB1/CB4 advance the same way regardless).

- **CB2 (PARTIAL, navigation tiers built → explanation remains).**
  Instead of a bare Kuzu web, CB2 becomes a batch: engineering expert(s) + heavy
  deterministic tools (AST-aware search, dependency-graph traversal, precise
  patch-apply) that **navigate** a repo larger than any context window rather
  than ingest it. Those navigation tiers now exist. Full PASS still needs the
  architectural explanation layer proven through the acceptance harness; raw
  graph/tool results are insufficient. Still propose-first for structural work.
- **CB3 / EB3 (PARTIAL, graph substrate built → media batch over the shared
  graph).** The knowledge-web dependency for shared entities/relationships is
  now satisfied (see both benchmarks' detail sections above); what remains is
  the media EXTRACTION pipeline (§3.4) itself — the batch layer supplies the
  coordinating media batch once that pipeline exists.
- **CB6 (PASS, ongoing discipline).** Batches must stay contract-compatible with each
  other and the central orchestrator — the same Integration-Contract discipline,
  applied *internally between batches*. This makes CB6 a live, ongoing test of the
  batch layer, not just the frontend/backend seam.
- **CB1 / EB2 (PARTIAL → prerequisite for the whole thing).** The persistence +
  compaction that let a weeks-long batch-coordinated mission survive session
  restarts *are* CB1/EB2. Fact/assumption + `valid_at` typing landed; explicit
  supersession linkage and explanation remain foundational gaps.

**Sequencing:** batch work remains owner-gated and propose-first. Current
cross-role ordering lives in `docs/ROADMAP.md`; do not revive this diagnosis's
old CB5 → CB1 → CB4 sequence.
