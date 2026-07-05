# Repository Intelligence

> **Purpose:** The architecture home for Attention Threshold **Pillar 3 —
> Repository Intelligence**: understanding systems larger than a context window
> without prompt-stuffing.
> **Scope:** Repository ingestion into navigable graphs (file, dependency,
> architectural, decision, ownership) and the reasoning that answers
> "what breaks if X is removed / what depends on Y / why was Z chosen."
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** 🛠 **PARTIALLY BUILT.** The **dependency-graph slice** is built: the
> `GraphPort`/Kuzu substrate (`core/memory/graph_store.py`, `graph_manager.py`) + the
> ast import-graph extractor, answering `depends_on` / `dependents_of` /
> `breaks_if_removed` over a real repo (53 graph tests; demo
> `scripts/cb2_repo_intelligence_demo.py`; the CB2 benchmark harness is in progress).
> The **remaining graphs** (file, architectural, decision, ownership) and
> natural-language explanation remain the target spec below — unbuilt. Tracked by
> [../../decisions/proposed/0008-repository-intelligence.md](../../decisions/proposed/0008-repository-intelligence.md).
> **Related:** [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
> (Pillar 3) · [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
> (Critical Benchmark 2) · [../knowledge_graph/](../knowledge_graph/) ·
> [../memory/](../memory/)

## Why this home exists

Repository Intelligence is one of the four pillars in
[ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md) and is tested by
**Critical Benchmark 2** — yet before this document it had **no architecture home
at all** (audit coverage score: 1/5, "mentioned"). A named pillar with no
discoverable home is an onboarding and drift risk: a new agent cannot find where
the capability is supposed to live. This README is that home.

## Target capability (from the pillar)

The system must answer, **without loading the whole repository into a prompt**:

- What would break if component X disappeared?
- Which services depend on Y? Which are transitively dependent?
- Why was architecture Z chosen? What boundaries currently exist?

## Target architecture (proposed)

Per ATTENTION_THRESHOLD Pillar 3, repository ingestion produces these graphs:

- **File graph** — files and their relationships.
- **Dependency graph** — imports/exports and transitive dependence.
- **Architectural graph** — components and boundaries.
- **Decision graph** — why structures exist (ties to `decisions/` + memory).
- **Ownership graph** — who/what owns each part.

**Forbidden:** reasoning by "massive prompt stuffing" (ATTENTION_THRESHOLD,
Pillar 3). The whole point is graph-backed reasoning over context-window-bounded
ingestion.

## Relationship to other subsystems

- Feeds and overlaps the [knowledge graph](../knowledge_graph/) (same
  entity/relationship substrate, scoped to a codebase).
- Decision/ownership graphs connect to [memory](../memory/) and
  [../../decisions/](../../decisions/).

## What is NOT claimed

The **dependency graph** is built (the thin slice — import/dependency edges +
depends-on / breaks-if-removed traversal over Kuzu). The **file, architectural,
decision, and ownership** graphs are NOT, nor is natural-language architectural
explanation (that is an LLM-synthesis layer above the graph, not the substrate).
Do not present the full pillar as shipped until Benchmark 2's pass requirements are met.
