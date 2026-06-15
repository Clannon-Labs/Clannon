# ARCHITECTURAL CONVENTIONS

> **Purpose:** The single home for *how code is placed and wired* — the rules an
> agent needs when **adding or moving** code. Distinct from invariants: these are
> "how to build it correctly," not "what must never break."
> **Scope:** Layer boundaries, entry points, dependency direction, provider
> isolation, transport, naming/placement, doc rules, and change management.
> **Authority level:** Cross-cutting (subordinate to
> [../vision/INVARIANTS.md](../vision/INVARIANTS.md) and
> [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md); above implementation/code).
> A convention may be overridden only by an Invariant or an accepted ADR.
> **Related:** [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) ·
> [INVARIANT_OWNERSHIP.md](INVARIANT_OWNERSHIP.md) ·
> [../glossary/TERMS.md](../glossary/TERMS.md)
>
> **Sources (consolidated, not invented):** project root `CLAUDE.md`
> ("Architectural Conventions" + "Hard Constraints") and the boundary prose in
> `SYSTEM_ARCHITECTURE.md` (Foundation Layer, LLM Framework Layer). The terse
> always-loaded list in `CLAUDE.md` is the enforcement subset; **this document is
> the full reference.** If the two ever diverge, reconcile here and update both.

---

## 0. Authority & relationship to INVARIANTS

- **INVARIANTS** (`vision/INVARIANTS.md`) = rules that must never be violated.
- **CONVENTIONS** (this doc) = how to place and connect code so the invariants
  hold and the system stays legible.
- Every convention below traces to a source. Do not add one without a source and
  a real placement/ownership need.

## 1. Layer Boundaries

**Rule:** Shared logic lives at the **nearest common access point of its users**.
If two parts use it, put it where both reach it cheapest; if most of the system
uses it, it belongs in `foundation`. `foundation` stays framework-light and
provider-neutral — it must not own business logic, sanitizer logic, memory
retrieval policy, or provider SDK calls. Never create circular imports.

*Source:* `CLAUDE.md` Conventions #1; `SYSTEM_ARCHITECTURE.md` Foundation Layer.

## 2. One Entry Point Per Layer

**Rule:** Each layer/sub-layer connects to the rest of the system through a
**single door** (e.g. `intake.process`, `verifier.run`, `orchestrator.run`;
inside the orchestrator, `experts/` and `tools/` each have their own handler
door). Internals live in `utils/`/subfolders. A layer's `__init__.py` exports its
entry point **only** when another part must import it directly — and only when
Flow can't carry the data instead.

*Source:* `CLAUDE.md` Conventions #2.

## 3. Dependency Direction Rules

**Rule:** Dependencies point **inward/downward** toward `foundation`.
`foundation` imports nothing else in the system. Stages may import shared
contracts from `foundation`, but never each other's internals. The LLM
framework, memory internals, and the Redis client are leaves behind seams (see
§4), not things stages reach around.

*Source:* `SYSTEM_ARCHITECTURE.md` Foundation Layer + Architectural Conventions;
`CLAUDE.md` Conventions #1/#3/#4.

## 4. Provider Isolation Rules

**Rule:** Every provider SDK lives behind a **Clannon-owned seam**, confined to
one module, so it can be swapped/audited from one place:

- **LLM framework** → confined to `core/llm` (entry `framework.py`). No other
  module imports `pydantic_ai`. *(Verified holding in production code.)*
- **Memory** → reached only through its Manager (`core/memory`); callers hold
  only `foundation.MemoryPort`. Nothing imports memory internals.
- **Redis** (when built) → behind its own seam module; stages call named
  functions (`reserve_budget`, `get_session`…), never raw `redis-py`.

*Source:* `CLAUDE.md` Conventions #3/#4; `SYSTEM_ARCHITECTURE.md` LLM Framework
Layer; `storage/REDIS_ARCHITECTURE.md` §9.

## 5. Flow vs. In-Layer Contracts

**Rule:** **Flow** is the inter-stage transport ("the system's fiber"). Between
stages, runtime payloads move only through `Flow.load/next/block/warn/fail` —
never free-form text. **Inside** a layer, agents/tools/experts exchange typed
contracts (Pydantic/dataclasses), but **not every sub-call is wrapped in a
Flow** — only stage boundaries are.

*Source:* `CLAUDE.md` Conventions #5 + Hard Constraints #1; `SYSTEM_ARCHITECTURE.md`
Core Architecture.

## 6. Naming & File Placement

**Rule:** Follow the deploy split — `backend/` (Railway) and `frontend/`
(Vercel). New subsystems get a folder with a single door; their detailed docs get
a folder under `docs/architecture/<subsystem>/` with a `README.md` entry point.
The **authoritative current layout** is `CLAUDE.md` → "Repository Layout"; the
intended/target layout is `docs/architecture/structure/`.

*Source:* `docs/architecture/structure/` + `CLAUDE.md` Repository Layout.

## 7. Documentation Rules

**Rule:** Every major doc carries a header: **Purpose, Scope, Authority level,
Related**. Subsystem folders carry a `README.md` entry point. Only document
**proven, tested** decisions — speculative choices stay out of docs until proven,
and aspirational capabilities are explicitly marked "proposed / not yet
implemented" (never described as existing).

*Source:* `CLAUDE.md` "Keep Docs Current" + the `docs/` header convention
established across this tree.

## 8. Change Management (ADRs)

**Rule:** No critical architectural decision may exist solely in code — every
important decision is an artifact in `docs/decisions/`. New decisions are
recorded as ADRs (proposed → accepted; or rejected); superseded ones move to
`deprecated/`. The core loop stays UI-agnostic: UIs connect to the loop and the
decision-log sink and exchange data only.

*Source:* `CLAUDE.md` Conventions #6; `vision/ATTENTION_THRESHOLD.md` Founder
Responsibility; `decisions/README.md`.
