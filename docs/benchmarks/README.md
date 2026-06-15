# Benchmarks

> **Purpose:** Explain why benchmarks exist, how they relate to the architecture,
> and when to consult them.
> **Scope:** The capability bars Clannon must clear before it is shown to anyone.
> **Authority level:** Tier 6. Benchmarks measure **outcomes**, not design. They
> validate the architecture; they do not dictate how it is built. A benchmark
> never overrides an Invariant, the Attention Threshold, or the architecture.
> **Related:** [../vision/ATTENTION_THRESHOLD.md](../vision/ATTENTION_THRESHOLD.md) ·
> [../vision/GOALS.md](../vision/GOALS.md) · [../00_START_HERE.md](../00_START_HERE.md)

## Contents

- **[CLANNON_V1_ATTENTION_THRESHOLD.md](CLANNON_V1_ATTENTION_THRESHOLD.md)** —
  the V1 capability bar: 6 Critical Benchmarks (required) + 3 Exceptional
  Benchmarks (differentiators), demo-readiness requirements, and the outreach
  gate.

## Why benchmarks exist

The architecture describes *how* Clannon is built. The benchmarks describe *what
it must be observably able to do* before it earns attention. They turn the
[Attention Threshold](../vision/ATTENTION_THRESHOLD.md) from a philosophy into a
pass/fail checklist, so "is it good enough to show?" is an objective question, not
a feeling.

## How benchmarks relate to the architecture

- **Outcomes, not implementation.** A benchmark says "a new session must
  reconstruct project state without chat history." It does **not** say which data
  structure or model achieves that — that is the architecture's job.
- **Each demonstration pillar maps to benchmarks.** The four pillars in the
  Attention Threshold (persistent memory, cross-media knowledge graph, repository
  intelligence, agent civilization) are what the Critical Benchmarks test.
- **They gate outreach, not design freedom.** Failing a benchmark means "don't
  show it yet," not "rewrite the architecture." If a benchmark is unreachable by
  the current architecture, that tension is escalated to the founder and (if it
  changes a decision) recorded in [../decisions/](../decisions/).

## When to consult benchmarks

- **Before any public, investor, researcher, or technical outreach** — the
  outreach gate is defined here.
- **When deciding what to build next** — prioritize work that moves a Critical
  Benchmark from fail to pass.
- **When evaluating whether a capability is "done"** — "done" means the relevant
  benchmark's pass requirements are met, not that code merely runs.

## Pass rule (summary)

Clannon may be shown publicly only after **all Critical Benchmarks pass and at
least one Exceptional Benchmark passes**, and the full capability is
demonstrable in a single uninterrupted 90–180s run with no hidden setup. The
authoritative criteria are in the benchmark document itself.

## Adding new benchmarks

Name versioned benchmark suites `CLANNON_V<n>_<THEME>.md`. Keep each criterion in
the outcome-first shape used by V1: Objective → Setup → Test Procedure → Pass
Requirements → Failure Conditions.
