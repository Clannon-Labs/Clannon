# `api/` — the frontend-facing surface

**Frontend: this is your doc.** Build against it. It does not change when the backend
is rewritten in Rust (`../rust/DECISIONS.md` D6), so the migration is not a reason to
pause, wait, or guess.

| File | What |
|---|---|
| [`ROUTES.md`](ROUTES.md) | All 38 routes — method, path, auth, purpose, and the semantics you cannot infer from a signature |
| [`requests/`](requests/) | **Your write channel.** Need a route that does not exist? File it here |

## What is authoritative, and what is not

| Question | Ask |
|---|---|
| Does route X exist, what does it return, what breaks it? | `ROUTES.md` |
| What SSE events exist and what keys do they carry? | `backend/api/README.md` + `backend/tests/benchmarks/fixtures/sse_contract.json` — machine-checked, see below |
| What does the ledger/hydration/seal *mean* in the UI? | `reports/INTEGRATION_CONTRACT.md` (being merged into here) |
| How does the frontend client itself work? | `frontend/BACKEND_INTEGRATION.md` §0 — still correct, still the frontend's own file |

**SSE is deliberately not restated here.** `sse_contract_drift.py` already forces the
frontend fixture, `backend/api/README.md`, and every backend emit site to agree. A
copy in this directory would be a fourth source that nothing checks. Link, never copy
— `ROUTES.md` §2 has the reasoning and the incident that proves it.

## Superseded

`frontend/BACKEND_INTEGRATION.md` calls itself *"complete, authoritative,
self-contained"* and tells you not to read backend code. **For routes and response
shapes, this directory supersedes it.** For frontend-internal architecture — the
`ClannonClient` interface, mock/http, `src/config/` — it is still right, and it is the
frontend's file to maintain. The backend does not edit it.
