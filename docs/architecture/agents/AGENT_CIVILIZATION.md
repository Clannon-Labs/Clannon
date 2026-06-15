# Agent Civilization

> **Purpose:** The architecture home for Attention Threshold **Pillar 4 — Agent
> Civilization**: many agents that read as one coherent organization, whose
> decisions survive sessions and stay explainable.
> **Scope:** The inter-agent **institutional artifact protocol** (agents
> communicate through durable artifacts, never hidden context) and the
> requirement that decisions/objections remain reconstructable later.
> **Authority level:** Tier 5 (Subsystem). Lives under
> [README.md](README.md) (the agents subsystem); inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** ⚠️ **PROPOSED — not implemented.** The institutional artifact
> protocol (RFC/Decision/Objection/…) is not built. Tracked by
> [../../decisions/proposed/0009-agent-civilization-artifact-protocol.md](../../decisions/proposed/0009-agent-civilization-artifact-protocol.md).
> **Related:** [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
> (Pillar 4) · [../memory/](../memory/) (promotion priority) ·
> [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
> (Critical Benchmark 6) · [../../glossary/TERMS.md](../../glossary/TERMS.md)

## ⚠️ Terminology collision — read first

The word **"artifact" means two different things** in Clannon, and conflating
them is an active source of architectural drift:

- **Output artifact** (`ArtifactStore` / `ArtifactRef`) — a delivered *file* an
  expert produces (e.g. `report.md`); **built**.
- **Institutional artifact** — a durable unit of *inter-agent reasoning* (RFC,
  Decision, Objection, Investigation, Contract, Migration, Risk); **PROPOSED —
  no implementation**, the subject of this pillar.

This document concerns the **institutional** artifact. The **canonical**
disambiguation — including the exact code location of the unrelated
`ArtifactStore` — is the single source of truth in
**[../../glossary/TERMS.md](../../glossary/TERMS.md)**; the two lines above are a
summary, not a second definition.

## Why this home exists

Pillar 4's runtime (orchestrator, experts, tools) is documented in
[README.md](README.md), but the "civilization" dimension — agents communicating
through artifacts and decisions surviving/explaining across sessions — had **no
home** and was only described in the vision doc (audit coverage score: 2/5),
compounded by the artifact term collision above.

## Target capability (from the pillar)

- **Communicate through artifacts, never hidden context** (ATTENTION_THRESHOLD,
  243–249).
- Weeks later, the system can explain **who decided, why, who objected, and what
  changed** (ATTENTION_THRESHOLD, 227–239).
- Required institutional artifact types: **RFC, Decision, Objection,
  Investigation, Contract, Migration, Risk** (ATTENTION_THRESHOLD, 251–267).

## Relationship to other subsystems

- **[memory/](../memory/)** — institutional artifacts are the high-priority
  memory types; the promotion priority Decision > Contract > Risk > Finding >
  Conversation (an **aspirational** invariant — see
  [../INVARIANT_OWNERSHIP.md](../INVARIANT_OWNERSHIP.md) §I.2, **not yet
  implemented**) would be the storage-side expression of this pillar.
- **[../../decisions/](../../decisions/)** — the ADR system is the *human-facing*
  instance of "decisions as durable artifacts"; the agent-facing protocol mirrors
  it.

## What is NOT claimed

No institutional-artifact protocol exists in code. Multi-agent coordination today
is the orchestrator/expert runtime only. Do not present Pillar 4 as shipped until
Benchmark 6 passes.
