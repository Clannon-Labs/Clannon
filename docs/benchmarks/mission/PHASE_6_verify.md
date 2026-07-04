# Phase 6 — Verify   STATUS: ongoing (applies to every commit)

- [ ] Full backend suite green BEFORE every commit (no exceptions — a prior pass
      committed before its suite ran; do not repeat).
- [ ] Add a test for every reliability + contract fix + every benchmark advanced.
- [ ] Re-run the latency baseline; confirm no regressions.
- [ ] Run both review subagents (security-review, architecture-boundary); fold
      findings into the report; never merge past a security-invariant violation.
- [ ] Confirm zero edits under frontend/; confirm the frontend was not woken
      improperly.
- [ ] Update CLANNON_V1_ATTENTION_THRESHOLD.md status per benchmark with links to
      proving tests.
