# Phase 2 — Latency & Streaming Feel   STATUS: not started (needs running stack)

**Goal:** feed the frontend's motion pass smooth, well-timed data.

- [ ] Measure time-to-first-decision-entry + time-to-first-token (needs Qdrant +
      an LLM key; be honest — do NOT fabricate numbers).
- [x] Confirm the decision-log stream flushes incrementally (not one end burst) —
      structural trace of on_event live vs deferred (api/run_state.emit, sse.py).
- [ ] Cheap deterministic gates precede expensive LLM calls without blocking
      stream start.
- [ ] Report streaming avoids UI layout-jump (stable structure early).
- [ ] Latency baseline table (hydration ms / first-entry ms / end-to-end).

**Acceptance:** incremental-flush verified structurally + a baseline table (or an
honest "requires live stack" note where numbers need running services).
