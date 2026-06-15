# core/orchestrator/ — the Vraksha-owned reasoning loop

Owns one orchestration turn: hydrate memory, run a native tool-driving agent over
the capability gateway, stream a decision log, produce a draft response. UI-agnostic.

## NEVER
- The orchestrator NEVER receives raw expert output. Experts buffer full
  `ExpertFindings` to `ctx.expert_findings`; only a brief `ExpertSummary` returns
  to the model (the two-output split — keeps orchestrator context lean across
  multi-expert turns). Hard constraint.
- It streams its structured decision log DIRECTLY to the user, live; only the final
  report buffers through the output filter. Never route the decision log through
  the filter; never stream a final report the filter hasn't accepted.
- It does NOT import tool/expert implementations or the registry. It's handed the
  Capabilities gateway (`ports.caps`), the `MemoryPort`, and the log sink at runtime.
  Tools/experts reach the model only as guarded native-tool wrappers (every
  grant / permission / SSRF / NETWORK-output-sanitize / output-cap guard still applies).
- It never content-blocks and never runs shell/file ops directly — handlers own
  the execution boundary.

## Conventions
- `orchestrator.py` = stage door (builds ports, applies the whole-turn timeout,
  stores draft + memory proposal). `loop.py` = hydrate → `ports.caps.run_turn` →
  map `OrchestratorAnswer` to `OrchestratorResponse`. Own contracts in `schemas.py`;
  ports in `ports.py`; internals in `utils/`.
- Bounds: `ORCHESTRATOR_MAX_TURNS` (cap forces a final answer), `ORCHESTRATOR_TIMEOUT_S`
  (fails closed). Memory is augmentation, never a gate — a hydration fault degrades
  to an empty package with an honest decision-log note. `orchestrator` prompt is unlocked.

## Tests
`tests/orchestrator_*.py` (loop, ports, stage, experts, tools, registry, recovery).

## Authoritative docs
`core/README.md` → Orchestrator; `docs/architecture/SYSTEM_ARCHITECTURE.md` → Orchestrator.
