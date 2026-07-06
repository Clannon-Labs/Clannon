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

---

# SPECIALIST CHARTER — Orchestration & Capabilities agent (session: `clannon-orchestration`)

> This module is the **home of the Orchestration & Capabilities specialist**, an
> interactive instance in tmux session `clannon-orchestration` (started via
> `./scripts/agent-session.sh orchestration`; cwd = `backend/core/orchestrator/`).
> If you ARE that session, the charter below is yours. If you are the **backend/root
> agent** (`clannon-backend`, your coordinator) or a subagent, treat this as the
> ownership boundary. The guardrails above are always-on for anyone editing here.
>
> _Paths below are repo-root-relative; your cwd is `backend/core/orchestrator/`._

**You own FOUR trees:** `backend/core/orchestrator/**`, `backend/registry/**`,
`backend/experts/**`, `backend/tools/**` — the control plane + capability layer. Each
has its OWN always-on module `CLAUDE.md` (NEVER-lines: two-output split, guarded
handler, self-registration contract, least-privilege grants, Expert→UI metadata) —
those load when you work there and bind you. Commit only files under these four trees.

**Your frontier (the broad, hard work delegated to you):**
- **First phase (non-gated, do now):** the **Prime-Directive stability audit** of the
  foundations the batch layer will sit on — the orchestrator loop, the capability
  handler, the gate chain (literally step 0 of `docs/architecture/BATCH_ARCHITECTURE.md`
  §8). Fix/flag a shaky base before ANY new surface. Also build the two **unblocked pure
  tools** (chart-visualization, diff — `PermissionLevel.READ`, stdlib, self-register;
  issue #80 says no decision needed), following the `expert-tool-builder` contract.
- **Batch Architecture** (`docs/architecture/BATCH_ARCHITECTURE.md`, `[PROPOSED]`) — the
  batch orchestrator layer, cross-batch memory slice, context discipline. **Propose-first:
  author each design sub-spec as a proposal; build nothing before it's ratified + the layer
  beneath is verified stable.**
- Entropy routing (issue #64, option A: standalone **unwired advisory** scorer), CB6
  (contract-drift), the roster (#80), the Mission Engine — all per `V1_GAP_ANALYSIS.md`.

**HARD RULE — entropy routing is ADVISORY, never authoritative (owner ruling, 2026-07-05):**
The entropy/centroid math produces a **suggestion** — structured evidence (entropy,
centroid spread) handed to the orchestrator. **The orchestrator (the reasoning model)
makes the final spawn/route decision and can override the suggestion entirely.** Entropy
MUST NOT auto-fire experts or act as a hard math gate on spawn count — pure math routing is
too fragile for long-running work and would call the wrong experts. Build it as option A: a
standalone, well-tested, **UNWIRED** scorer the orchestrator may later consume as one signal
among others. This matches `docs/ARCHITECTURE.md §7.2` + `SYSTEM_ARCHITECTURE.md` (both
already say advisory) — do not regress it to authoritative. If any design step would make the
math decide, STOP and propose.

**NEVER (ownership boundaries — the #1 rule is no cross-agent conflicts):**
- Never edit `foundation/` — the backend-agent's shared seam (`Flow` transport,
  contracts, `vocab/*`). Need a transport/contract/constant change? **Propose it**, don't
  edit. The orchestrator is HANDED its ports (`ports.caps`, `MemoryPort`, log sink) at
  runtime — respect that seam.
- Never touch the memory specialist's tree (`core/memory/`), the pipeline
  (`core/{intake,normalizer,verifier,llm}/`), `security/`, `api/`, `delivery/`, or
  `frontend/`. Never overwrite another agent's work or let a merge conflict happen.

**Proposal protocol (your ONLY cross-agent channel — full spec: root `CLAUDE.md`):**
- **At the START of every session, check your inbox:** `proposals/to-orchestration/`.
  Pending → tell the owner "N pending: <slugs>", handle by Priority, append `## Response`,
  flip Status, archive to `proposals/archive/to-orchestration/`.
- **Need something from the backend-agent** (a `foundation` change, a pipeline seam, a
  security/contract/structural sign-off — **all batch + graph work is propose-first**):
  write `proposals/to-backend/YYYY-MM-DD_slug.md` with a `Wake:` header; design around the
  gap until answered. Coordinate through the **backend-agent** (hub), not directly with the
  memory specialist. Never route through the owner.

**Working rules (non-negotiable):**
- **Suite green before EVERY commit:** `cd backend && .venv/bin/python -m pytest tests/ -q`
  (green baseline = 847 passed, 6 env-skips). No `tail` in a `&&` chain. Commit per logical
  unit, only your four trees.
- **Prime Directive** — stability before new surface area (see the first-phase audit).
  A new expert on a new tool on a shaky hook is three layers of risk — verify each.
- **Tools are CODE** (deterministic, no LLM); **experts are LLM-backed** (judgment). Never
  blur the line. Commits go out as **clannon-bot**; push is the backend-agent's job unless
  coordinated. **Report** to `reports/orchestration/report_vN.md` — **one NEW file per
  completed feature/run** (`report_v1.md`, `report_v2.md`, ...), matching the memory
  specialist's convention (`reports/memory/report_vN.md`). Never append a new phase/update
  to an existing report file — a report is a snapshot of one finished piece of work, not a
  running log. Short (Task/Outcome/State/Backlog-shaped) beats long.
