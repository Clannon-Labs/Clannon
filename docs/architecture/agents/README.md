# Agents — Orchestrator, Experts & Tools

> **Purpose:** Entry point for how Clannon reasons and acts — the orchestrator
> loop, the experts it spawns, and the tools they call.
> **Scope:** Orchestration, expert roster, tool roster, the LLM adapter that
> drives them, and entropy-based expert routing *(PROPOSED — not built; see
> [../../ARCHITECTURE.md](../../ARCHITECTURE.md) §7.2)*. Excludes memory (see
> [../memory/](../memory/)) and security gates (see [../security/](../security/)).
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [../memory/](../memory/) · [../security/](../security/) ·
> [../../glossary/TERMS.md](../../glossary/TERMS.md)

## Contents

- **[EXPERTS_AND_TOOLS.md](EXPERTS_AND_TOOLS.md)** — the full target roster
  (~11 experts, ~16 tools): what each one does and the expert-vs-tool
  distinction.
- **[AGENT_CIVILIZATION.md](AGENT_CIVILIZATION.md)** — Attention Threshold
  Pillar 4: the institutional artifact protocol (RFC/Decision/Objection/…) by
  which agents read as one organization. **Proposed / not built**; includes the
  "artifact" terminology disambiguation.

## Canonical design

The authoritative design lives in [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md):

- **Orchestrator** — central reasoning layer; Clannon-owned loop where the model
  is a structured *advisor*, not the driver.
- **Decision Log Streaming** — structured decision commentary streamed live.
- **Expert Spawning: Entropy-Based Routing** *(PROPOSED — not built)* — the target:
  Shannon entropy over domain centroids surfaced as an advisory signal. Today spawn
  count is whatever the model emits (`ORCHESTRATION_ANALYSIS.md:48`).
- **Expert Communication Contract** — brief summary to the orchestrator, full
  findings to the output pipeline.
- **Control Model And Contracts** — `OrchestratorDecision`, `DecisionLogEntry`,
  `ExpertSummary` / `ExpertFindings`, tool permission handler, turn/timeout bounds.
- **Experts And Sub-Agents** — least-privilege specialist workers.
- **LLM Framework Layer** — PydanticAI behind a Clannon-owned adapter, confined
  to `core/llm`.

## Implementation

- `backend/core/orchestrator/` — the loop, schemas, ports, decision log.
- `backend/registry/` — capability machinery: `@tool` / `@expert` decorators,
  store, discovery, the guarded Capabilities door.
- `backend/experts/` — expert packages (each co-locates its `system.md` + skills).
- `backend/tools/` — tool implementations.
- `backend/core/llm/framework.py` — the single LLM build/run entry point.

## Key invariants this subsystem must honor

- The orchestrator never receives raw expert output (context stays lean).
- Tools run under explicit permission checks, least-privilege, sandboxed.
- No free-form text between components — structured contracts only.
- The framework SDK never leaks outside `core/llm`.
