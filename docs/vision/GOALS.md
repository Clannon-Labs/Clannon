# GOALS

> **Purpose:** Answer "what is Clannon trying to become?" without requiring any
> architecture knowledge.
> **Scope:** Objectives, long-term vision, the Attention Threshold targets, and
> the capabilities that define success.
> **Authority level:** Tier 3 (Vision). Frames *whether* something should exist;
> yields to [INVARIANTS.md](INVARIANTS.md) and [ATTENTION_THRESHOLD.md](ATTENTION_THRESHOLD.md).
> **Related:** [00_START_HERE.md](../00_START_HERE.md) ·
> [ATTENTION_THRESHOLD.md](ATTENTION_THRESHOLD.md) ·
> [../benchmarks/README.md](../benchmarks/README.md)

---

## In one sentence

Clannon aims to become the **memory-native workspace that remembers, understands,
and evolves a body of work over time** — taking on whole jobs end to end, and
getting *better* at a project the longer it lives with it.

## Project objectives

- **Automate whole workflows, not single tasks.** Take a brief and return a
  finished, quality-filtered deliverable: research, writing, coding, data
  analysis, media understanding, verification, and delivery — in one continuous
  workspace. Research was the first vertical; the product is the workflow engine.
- **Make the second session the magic.** A returning user should feel the system
  pick up exactly where they left off, surfacing relevant context before they
  re-explain anything. Continuity is the headline, not chat.
- **Earn trust through visibility.** Every memory shows its source and is one
  click from correction; every reasoning step streams as a structured decision
  log; every security decision is explainable.
- **Stay quality-safe for paying users.** Outputs pass a citation- and
  safety-aware filter before delivery. Paying users should never feel like they
  are debugging the system.

## Long-term vision

Clannon is **not** competing on any single axis:

- not trying to beat ChatGPT at chatting,
- not trying to beat Claude at coding,
- not trying to beat Perplexity at search.

It is becoming the system that **remembers, understands, and evolves projects
over time better than any of them.** The moat is secure, high-quality
*continuity* — a memory-native agentic workspace where a user keeps researching,
writing, coding, and creating without ever restarting context or managing
infrastructure. The moat is not a model, a framework, or a UI surface.

## The Attention Threshold objective

The near-term north star is crossing the **Attention Threshold**: the point at
which an experienced AI engineer, researcher, or investor watching a single
uninterrupted 3-minute demo concludes —

> "This is not a chatbot wrapper. This is not conventional RAG. This demonstrates
> capabilities unavailable in standard AI products."

Until that conclusion is reachable from the demo alone, outreach is deferred.
The strategy that gets there is captured in
[ATTENTION_THRESHOLD.md](ATTENTION_THRESHOLD.md) as four demonstration pillars:

1. **Persistent organizational memory** — remembers decisions, tradeoffs, failed
   approaches, assumptions, and reasoning, not just conversation.
2. **Cross-media knowledge graph** — PDF, image, audio, video, and code converge
   into one shared representation; the same entity across modalities is one
   entity.
3. **Repository intelligence** — reasons about systems larger than a context
   window without prompt-stuffing the whole repo.
4. **Agent civilization** — many agents that read as one coherent organization,
   whose decisions survive sessions and stay explainable.

## Target capabilities (what success looks like)

Concretely, Clannon "works" when it can, on demand and in a demo:

- Reconstruct a project's state, open decisions, risks, and historical reasoning
  in a brand-new session **with no prior conversation history**.
- Ingest mixed media about one project and answer questions that require evidence
  from **multiple modalities at once**, with provenance and contradiction
  detection.
- Explain a large repository's dependencies and architectural boundaries
  **without loading it into a single prompt**.
- Preserve **why** a decision was made — alternatives, risks, participants —
  weeks later.
- Behave safely under adversarial input (prompt injection, memory poisoning,
  tool abuse) and **explain** every security decision.
- Stay architecturally consistent when **multiple specialized agents** work in
  parallel.

The pass/fail definition of these is owned by the benchmarks, not by this file —
see [../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md).

## Commercial shape

Clannon ships as a **hosted SaaS** for freelancers and small agencies, priced in
tiers (Free / Starter / Pro / Agency) with usage-based token budgets per tier.
Memory tiers unlock progressively across plans; episodic memory is always on.
The detailed tiering, budgets, and billing mechanics live in
[../architecture/SYSTEM_ARCHITECTURE.md](../architecture/SYSTEM_ARCHITECTURE.md)
(Token Budget System, Memory Tier Access) and
[../architecture/storage/REDIS_ARCHITECTURE.md](../architecture/storage/REDIS_ARCHITECTURE.md).

## Current build phase

**Production.** The product runs end to end. The earlier "Macondo Checkpoint"
gating phase is complete and retired — see
[../decisions/deprecated/0007-macondo-checkpoint-build-phase.md](../decisions/deprecated/0007-macondo-checkpoint-build-phase.md).
The active roadmap priority is: **one impressive end-to-end workflow → no-signup
demo → cloud deployment (multi-tenancy, billing) → frontend polish.** Major new
feature areas are confirmed with the founder before building.
