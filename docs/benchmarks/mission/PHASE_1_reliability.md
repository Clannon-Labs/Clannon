# Phase 1 — Reliability   STATUS: in progress

**Goal:** premium = never feels broken. Harden the reliability surface.

- [x] #52 manager gather/degrade guard — **already done** (report_v9, commit
      1812c33; xfail flipped to a passing test in tests/memory_store_fault.py).
- [x] **Memory persisted-only surfacing** (CB1 honesty): Manager returns what it
      ACTUALLY persisted (confidence floor + dedup can reject); run.memory_writes
      surfaces only that — never a phantom memory. record_write_proposals →
      return persisted records; api/run_driver.py maps only those.
- [ ] Dependency failure audit: Qdrant/embeddings/LLM/artifact-store/rate-limiter
      each fail CLOSED + HONEST (bounded timeout + degraded signal, no hang/500).
- [ ] Error-shape audit: every API error path returns the {"detail": ...} shape
      the frontend parses (report_v7 flagged PR #74 breaking it) — typed, never a
      bare string.

**Acceptance:** persisted-only memory + tests; a dependency/error-shape audit
table (gaps fixed or logged); suite green.
