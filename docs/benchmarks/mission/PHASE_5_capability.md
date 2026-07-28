# Phase 5 — Capability Work (close V1 gaps)   STATUS: in progress

**Goal:** advance benchmarks in priority order; every claimed PASS needs a
committed runnable proof (else it stays PARTIAL).

**Structural frame:** the `[PROPOSED]` **Batch Architecture**
(`docs/architecture/BATCH_ARCHITECTURE.md`, owner-authored) is largely HOW the
graph-blocked capabilities get built (esp. CB2 as an engineering batch). It is
propose-first + stability-first and does NOT jump the queue — near-term non-graph
wins (CB5/CB1/CB4) advance the same way regardless.

**Standing rule — Prime Directive (stability before new surface area):** before
building ANY new capability, verify the layer beneath it is stable/correct/honest
(not just "tests pass"). Shaky foundation ⇒ STOP, fix or flag first; absorb big
foundation fixes into the plan as prerequisites, never silently.

- [ ] **CB5**: close the detect residual and widen the c5 battery. Structured
      classify/explain output and earned-seal surfacing have landed.
- [ ] **CB1** (+EB1, also a batch-architecture prerequisite):
      fact|assumption + `valid_at` typing landed. Add retrieval explanation,
      complete provenance, and explicit supersession linkage; extend c1 + e1
      harnesses to PASS.
- [x] **CB4 audit mirror** (+CB6/EB2): durable structured decision records and
      owner-scoped endpoint landed. Benchmark remains PARTIAL: structured
      tradeoffs/history and complete crash-path participants remain open.
- [x] **CB6**: Integration Contract + enforcing contract-drift test.
- [ ] **CB2/CB3/EB3** — Kuzu graph, CB2 symbol/AST/dependency/archive tiers
      landed. CB2 explanation and real media ingestion remain open.
      **Propose-first — the spec exists (docs/architecture/BATCH_ARCHITECTURE.md,
      PROPOSED); do NOT build without proposing each sub-layer and passing the
      stability gate.** Build sequence in that doc §8.

**Acceptance:** each advanced benchmark has a committed proving test; the batch
architecture stays a proposed spec until its build sequence is approved.
