# Phase 6 — Verify   STATUS: ongoing (applies to every commit)

- [ ] Full backend suite green BEFORE every commit (no exceptions — a prior pass
      committed before its suite ran; do not repeat).
- [ ] Add a test for every reliability + contract fix + every benchmark advanced.
- [ ] Re-run the latency baseline; confirm no regressions.
- [ ] Run both review subagents (security-review, architecture-boundary); fold
      findings into the report; never merge past a security-invariant violation.
- [ ] Confirm zero edits under frontend/; communicate through pull-based
      proposals only, per `docs/architecture/CREW_WORKFLOW.md`.
- [ ] Update the benchmark verdict in `V1_GAP_ANALYSIS.md` — with a link to the
      proving test — in the SAME commit as the work.
      **Not** in `CLANNON_V1_ATTENTION_THRESHOLD.md`, which this checkbox used to
      say. That file is the owner's spec of the bar (what a benchmark must
      demonstrate); it deliberately carries no per-benchmark status. Adding
      status there would make a fourth status surface, and duplicated status is
      exactly what rotted here — on 2026-07-28 the priority order in `CLAUDE.md`
      and the verdicts in the gap analysis had drifted apart and were sending
      agents at finished work. One verdict, one place.
