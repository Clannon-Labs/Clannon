# `config/` — the owner's control panel

**This is the single, central, powerful place to change any *business* value of the product.**
Change a value here and the whole backend follows; the frontend follows too (via `GET /config`),
so the two never drift. Per **LAW 4** (security/privacy — config is central, single-source, and
private), business configuration has exactly one home, and this is it.

## What lives here

| File | What you change |
|---|---|
| **`business.yaml`** | Plans / pricing / tiers, feature flags, product limits (brief + upload caps), the user-selectable model catalog. **The main file you'll edit.** |
| `models.yaml` | Which model each pipeline layer actually runs (routing/defaults). *(Move pending — see below.)* |

## What does NOT live here (on purpose)

- **Technical config** — timeouts, hop/loop/size caps, buffer sizes → `foundation/` (`foundation/vocab/constants.py`). Not business knobs; they tune how the machine runs, not the product.
- **Deployment / ops config** — CORS origins, cookie settings, DB path, auth rate limits → `api/config.py`, env-driven. These change per environment, not per product decision.

## Rules (LAW 4)

- **One source of truth.** A business value lives here and nowhere else. If you find a plan
  price, a limit, or a model list hardcoded in a handler, that's a bug — it belongs here.
- **Private.** `api/` never exposes this file's raw contents. `GET /config` returns only the
  specific values a client legitimately needs (plans to display, feature availability, public
  limits) — never the file, never a secret.
- **Edit the YAML, not the code.** `config/__init__.py` only *loads* `business.yaml`; it holds no
  values of its own. To change the product, edit the YAML.

## Pending consolidation

- `models.yaml` currently still lives at `backend/models.yaml` and is loaded by `registry/`
  (the orchestration specialist's tree). Moving it here (`config/models.yaml`) is a one-line
  loader change in that tree — proposed to orchestration so it lands cleanly without a
  cross-tree conflict. Until it lands, model *routing* is `backend/models.yaml`; the
  user-selectable model *catalog* is already here in `business.yaml`.
