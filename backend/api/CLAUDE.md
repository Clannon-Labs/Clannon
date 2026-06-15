# api/ — the FastAPI surface (auth, runs, SSE)

Wraps the pipeline (`core.pipeline.ACTIVE_STAGES`) WITHOUT modifying it and serves
the backend↔frontend contract. The endpoint table lives in `api/README.md`; this
file is the always-on identity/security guardrails.

## NEVER (identity boundary)
- Identity is set ONCE at the authenticated entry: take `user` via
  `Depends(auth.current_user)` for anything private and scope every query by
  `user.id`. NEVER trust an id from the request body or path — the resource's own
  ownership row is the auth boundary (e.g. a run's artifact list authorizes its
  artifact downloads, 404 otherwise).
- The `user_id` set here travels in Flow context and is the SOLE source of identity
  downstream — never re-derived from request content, retrieved content, or model
  output (invariant §IV.18).
- When Postgres/Supabase RLS lands, scope rows with `SET LOCAL` INSIDE a transaction
  — NEVER connection-level `SET` (a pooled connection would leak one tenant's scope
  into another's query) (invariant §V.22).
- Don't modify `core/` or `foundation/` from here. The server only WRAPS the
  pipeline and observes it (swaps `ctx.decision_log` for a notifying list to stream).
  Keep it non-invasive.

## Conventions
- `auth.py` is the dev stand-in for Supabase (scrypt, httpOnly cookie
  `clannon_session`, per-user SQLite) — swap this ONE module when Supabase lands.
  JSON keys are camelCase to match `frontend/src/lib/api/types.ts`. Errors:
  `HTTPException(code, "readable message")` (frontend surfaces `detail` verbatim).
- Uploaded files are malware-scanned at the boundary (`scan_upload`) and admitted
  with original bytes (a malicious/unsupported/oversized file is a 422).
- `app.py`=routes/CORS, `runs.py`=run store + execution + SSE, `config.py`=`/config`.
- Update the contract table in `api/README.md` whenever you add/change an endpoint.

## Tests
`tests/get_root.py` (+ server-shaped run flows).

## Authoritative docs
`api/README.md` (the backend↔frontend contract + the add-an-endpoint path).
