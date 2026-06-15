# Repository Structure

> **Purpose:** Entry point for how the codebase and deployment are laid out.
> **Scope:** Directory layout, the backend/frontend deploy split, and where each
> layer's single door lives.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [../../00_START_HERE.md](../../00_START_HERE.md) ·
> the project root `CLAUDE.md` (the authoritative *current* tree).

## Contents

- **[REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md)** — a target/reference
  directory tree for a clean production layout (Railway deploys `backend/`,
  Vercel deploys `frontend/`), including the foundation/core/pipeline/experts/
  tools/memory/delivery/api breakdown.

> **Authoritative source caveat:** the file above is a *reference target*, not a
> live map. The **actual current layout** is documented in the project root
> **`CLAUDE.md` → "Repository Layout"**, which reflects the real restructure
> (pipeline stages live under `backend/core/`, `server/` is now `backend/api/`,
> the registry/capabilities machinery, `get_root()` resolving to `backend/`).
> When the two disagree, **`CLAUDE.md` wins** for "where is the code today";
> this doc explains the intended shape and deploy boundaries.

## The rules the layout encodes

From [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) → Architectural
Conventions and the Invariants:

- **One entry point per layer/sub-layer** — internals stay in `utils/` /
  subfolders; a layer's `__init__.py` exports only its door.
- **Shared logic at the nearest common access point of its users** —
  system-wide primitives live in `foundation`.
- **Provider SDKs live behind a Clannon-owned seam** — LLM in `core/llm`,
  memory behind the MemoryPort, Redis behind its own module.
- **Deploy split** — `backend/` → Railway, `frontend/` → Vercel.
