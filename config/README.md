# `config/` — the control panel for the whole product

**This is the ONE place to change any tunable value in Clannon without editing code.** A tunable is
a knob a human might reasonably want to turn — a threshold, limit, timeout, budget, model choice,
feature flag, tier, or piece of copy. Not program logic. Change a value here and the whole system
follows; the frontend follows too (backend values via `GET /config`), so the two never drift.

Per **LAW 4** (security/privacy — config is central, single-source, private), every business value
has exactly one home, and this directory is it.

## Layout

```
config/
  README.md              this file
  models.yaml            all model IDs + per-role routing + fallbacks (moving in — see "pending")
  backend/               BACKEND-CONTROLLED — server-enforced, NEVER changeable from the frontend
    tiers.yaml           plans · pricing · feature flags
    limits.yaml          product input limits (brief + upload caps)
    model-catalog.yaml   which models a user can SELECT in Settings
    budget.yaml          the spend/margin ceiling + budget knobs (arriving with the Redis budget)
    ... (orchestrator · memory · experts · tools · security · llm · api · copy — arriving per area)
  frontend/              harmless user-facing cosmetics ONLY (theme · timings · display · copy · defaults)
```

## The one rule that matters most (LAW 4 — the security rule)

The frontend is a **mirror** of the backend, never a source of authority. For every value:

> "If a user bypassed the frontend and hit the backend directly, could a changed value here harm
> the backend, other users, security, or our margin?"

- **YES → it lives in `config/backend/`**, is enforced server-side, and is never changeable from the
  frontend (plans, limits, budget ceiling, security thresholds, model access, timeouts).
- **NO → it may live in `config/frontend/`** as a harmless preference the user is *supposed* to change
  (their theme, display density). Every frontend-exposed value still has backend-side validation, so a
  bypassed client cannot submit an illegal value and have it honored.

## Rules

- **One source of truth.** A value lives here and nowhere else. A plan price, a limit, or a model list
  hardcoded in a handler is a bug — it belongs here.
- **Private.** No code path (especially `api/`) exposes this directory's raw contents; `GET /config`
  returns only the specific values a client legitimately needs.
- **Edit the data, not the loader.** The backend reads these files through a typed, validate-at-startup
  loader (`backend/settings.py`) that fails loud on an invalid value; the loader holds no values of its
  own. To change the product, edit the YAML.

## What does NOT live here

- **Technical internals** — Flow/transport shapes, contracts, enums, error taxonomy → `foundation/`.
  (Product knobs that were mixed into `foundation/vocab/constants.py` are being moved OUT into
  `config/backend/*` — see `docs/config/CONFIG_INVENTORY.md`.)
- **Deployment/ops** — CORS, cookies, DB path, request-size + auth rate limits → env-driven in `api/`.
- **Secrets** — API keys come from the environment, never a file here.

## Pending consolidation (tracked in `docs/config/CONFIG_INVENTORY.md`)

Being externalized one area per commit, behavior-preserving. Done: plans/limits/model-catalog. Next:
model routing (`models.yaml`, multi-loader move), the `foundation/` product-knob move, budget ceiling,
then memory/orchestrator/tools/security/llm/copy, then `config/frontend/*` (frontend agent wires the UI).
