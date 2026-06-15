# 0007 — Macondo Checkpoint build-phase gating

> **Status:** deprecated
> **Date recorded:** 2026-06-15 (decision was active until Macondo submission)
> **Supersedes / superseded by:** superseded by the **Production** build phase
> (see [../../vision/GOALS.md](../../vision/GOALS.md) → Current build phase).
> **Authority:** Tier 7 (ADR). Historical — retained for reasoning only.

## Context

Before the product was opened to general production work, the build was gated to a
single submission target ("Macondo Checkpoint"). The architecture doc's lead
section enforced a strict in-scope list (core agent loop end to end, MemoryPort,
orchestrator bounds, reviewer-stable) and an out-of-scope list (full Memory
Manager, multi-tenancy enforcement, billing/Stripe, MCP, demo system, frontend),
with a hard rule to stop and ask before building anything out of scope.

## Decision (now deprecated)

The build phase gated work to the checkpoint scope and required explicit founder
approval to touch out-of-scope production features.

## Why deprecated

Macondo was submitted on 2026-06-12. The gating phase is complete and retired;
the out-of-scope list has opened up. The active phase is now **Production**, with
roadmap order: one impressive end-to-end workflow → no-signup demo → cloud
deployment (multi-tenancy, billing) → frontend polish.

## Original gating text (preserved verbatim)

This section previously led `SYSTEM_ARCHITECTURE.md`. It was removed from the
canonical architecture (it is project-phase/history, not architecture) and is
preserved here verbatim so the original scope boundary remains reconstructable:

> **ACTIVE BUILD PHASE: Macondo Checkpoint**
>
> **Current goal: reach the Macondo submission checkpoint. Do NOT build production
> features until this checkpoint is reached and I have confirmed submission.**
>
> **What the checkpoint includes (build ONLY these)**
> - The core agent loop running end to end: intake → sanitize → normalize →
>   verify → orchestrator (with at least 2 real working experts and 4 tools) →
>   output filter → delivery
> - Memory reached only through the MemoryPort (minimal working version of memory
>   is acceptable for the checkpoint)
> - Orchestrator bounds enforced (max turns, timeout)
> - Stable enough to run reliably for a reviewer
>
> **Explicitly OUT of scope until after submission**
> - Full Memory Manager implementation (belief layer, Lagrangian allocation, real hydration)
> - Multi-tenancy enforcement (Semgrep unscoped-query CI, Postgres RLS pooler discipline)
> - Token budget / billing / Stripe
> - MCP integrations
> - Demo system
> - Frontend
>
> **Build-scope rule (enforce every session)**
> Before writing or modifying code that implements anything in the OUT OF SCOPE
> list above, STOP and tell me explicitly:
> "This is a production feature outside the Macondo checkpoint: <name>. Do you
> want to proceed, or defer until after submission?"
> Do not proceed with out-of-scope work without my explicit yes.
>
> **Checkpoint-reached rule**
> When all items in "What the checkpoint includes" are met and stable, STOP and
> tell me clearly: "Macondo checkpoint reached — ready for you to verify and
> submit." Do not silently continue into production work.
>
> **After submission**
> Once I confirm Macondo is submitted, I will change this section to
> "ACTIVE BUILD PHASE: Production" and the out-of-scope list opens up.

## Source

Originally `SYSTEM_ARCHITECTURE.md` → "ACTIVE BUILD PHASE: Macondo Checkpoint"
(now removed from canonical; preserved above). Current phase:
[../../vision/GOALS.md](../../vision/GOALS.md) and project `CLAUDE.md` →
"ACTIVE BUILD PHASE: Production".
