# Phase 5 — Capability Work (close V1 gaps)   STATUS: not started

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

- [ ] **CB5** (do first, near-pass): close the detect residual + surface the
      verifier's classify/explain as structured output; widen the c5 battery.
- [ ] **CB1** (+EB1, also a batch-architecture prerequisite): additive
      fact|assumption + valid_at/superseded_by typing on MemoryWriteProposal/
      MemoryItem (ROBUST_MEMORY §7.4 additive contract) + surfaced retrieval "why";
      extend c1 + e1 harnesses to PASS.
- [ ] **CB4** (+CB6/EB2): durable decision-log audit mirror — persist the in-run
      decision log as structured records. **Propose-first** (new persistence
      surface). Extend c4 harness.
- [ ] **CB6**: batches (and the frontend seam) stay contract-compatible — the
      Integration Contract + a real contract-drift test.
- [ ] **CB2/CB3/EB3** — the Batch Architecture + Kuzu knowledge-web.
      **Propose-first — the spec exists (docs/architecture/BATCH_ARCHITECTURE.md,
      PROPOSED); do NOT build without proposing each sub-layer and passing the
      stability gate.** Build sequence in that doc §8.

**Acceptance:** each advanced benchmark has a committed proving test; the batch
architecture stays a proposed spec until its build sequence is approved.
