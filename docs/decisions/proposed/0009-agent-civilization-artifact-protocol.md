# 0009 — Agent Civilization artifact protocol (Pillar 4)

> **Status:** proposed
> **Date recorded:** 2026-06-15
> **Supersedes / superseded by:** —
> **Authority:** Tier 7 (ADR). Anchors
> [../../architecture/agents/AGENT_CIVILIZATION.md](../../architecture/agents/AGENT_CIVILIZATION.md).

## Context

Attention Threshold Pillar 4 requires agents to communicate through durable
**institutional artifacts** (RFC/Decision/Objection/Investigation/Contract/
Migration/Risk) rather than hidden context, and for their decisions to survive
and stay explainable (ATTENTION_THRESHOLD.md, 217–267; Critical Benchmark 6). An
audit found this dimension had no architecture home, and that the term "artifact"
collides with the unrelated `ArtifactStore` (delivered output files) — see the
canonical disambiguation in [../../glossary/TERMS.md](../../glossary/TERMS.md)
("Artifact" entry) for its exact code location.

## Decision (proposed)

Adopt `architecture/agents/AGENT_CIVILIZATION.md` as the home for the
institutional artifact protocol, and **disambiguate the term**: "output
artifact" (built, `ArtifactStore`) vs "institutional artifact" (proposed, this
protocol). The protocol's schema, storage, and tie-in to memory promotion
priority are **not yet ratified** — this ADR records intent, ownership, and the
terminology fix.

## Alternatives considered

- **Leave it in the vision doc only** — rejected: a core pillar with no
  architecture home is invisible to contributors and drifts.
- **Reuse the `ArtifactStore` contract for institutional artifacts** — rejected:
  different lifecycle and purpose (delivered files vs reasoning records);
  overloading one term/contract is the drift we are fixing.
- **New top-level `architecture/artifacts/` folder** — rejected as folder
  proliferation; the protocol is an agents concern, so it lives under `agents/`.

## Consequences & risks

- Pillar 4 becomes traceable; the artifact collision is documented and fixed in
  the glossary.
- Risk: implying the protocol exists — mitigated by the PROPOSED banner and the
  "what is NOT claimed" section.

## Source

[../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
→ Pillar 4; [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
→ Critical Benchmark 6. The colliding `ArtifactStore` and its code location are
defined canonically in [../../glossary/TERMS.md](../../glossary/TERMS.md) ("Artifact"
entry) — see there rather than restating the path.
