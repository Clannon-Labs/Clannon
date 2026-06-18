# docs/architecture/orchestration

Analysis and forward design for the orchestration layer
(`core/llm`, `core/orchestrator`, `registry/capabilities/handler`, `experts`, `tools`).

The **canonical** orchestrator design lives in
[`../SYSTEM_ARCHITECTURE.md`](../SYSTEM_ARCHITECTURE.md) → Orchestrator and
[`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md). Docs here do not
redefine it — they critique the implementation and propose changes.

- [`ORCHESTRATION_ANALYSIS.md`](ORCHESTRATION_ANALYSIS.md) — start here. Now a **forward build
  plan**: the **Track-A efficiency set is done** (kept as a one-line reference table), and the
  doc focuses on **what's left** — two deferred efficiency items (plan-then-parallel,
  programmatic tool calling) and the **Track-B V1 capability gate** (the spec-level plan for the
  new experts/tools/patterns that close [`../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md`](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md);
  memory layer scoped out as a separate workstream). Ends with a gate-first roadmap.
- [`EXTENSION_POINTS.md`](EXTENSION_POINTS.md) — the "drop-in kit": the single place that
  says exactly where each future gate capability plugs in, so you never scan the codebase.
  Most experts/tools are already drop-in (self-registration); three small one-time infra
  seams (stores, orchestration mode, security hooks) are specified, decision-agnostic, not
  yet built.
</content>
