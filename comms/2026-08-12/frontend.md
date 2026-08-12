# frontend — 2026-08-12

Headless `frontend-worker` dispatched by backend-coordinator, scoped to
`frontend/src/config/`, closing frontend-audit F-01 and F-02
(`proposals/to-frontend/2026-08-12_close-private-alpha-security-blockers.md`).

Verified both findings against current `dc2cd8e` source and
`reports/frontend-audit/report_v2.md` before touching anything — both confirmed true,
not assumed.

- **F-01**: `resolveApiMode()` now rejects `mock` whenever `NODE_ENV=production`
  (default read from `process.env.NODE_ENV`, overridable for tests). Missing/empty
  still defaults to `http` in every environment; unknown/case-mismatched values still
  throw in every environment. Proved with 4 real `next build` runs, exact exit codes:
  prod+unset→0 (http), prod+mock→1 (exact throw message), prod+http→0,
  case-mismatched→1.
- **F-02**: `normalizeHttpUrl()` now rejects credential-bearing URLs and malformed
  percent escapes (`%zz`, truncated `%2`, non-hex), mirroring
  `backend/api/run_sources.py`'s `_client_source_url` scan (read-only reference).
  Safe percent-encoded path/query values still pass. One shared function — SSE parsing
  and the render boundary both already call it, no second validator added.

Verified: focused test 30/30, full `npm test -- --run` 273/273, typecheck clean, lint
clean, four production builds proving F-01's safe/unsafe branches by exit code. No
Playwright run — this task has no visual UI change; the unit/build evidence already
covers every required branch, recorded explicitly instead of adding screenshots that
would prove nothing new.

Only the three owned config/test files changed. Left uncommitted per dispatch
mandate — coordinator reviews/commits/pushes. Full detail in the proposal response and
`.agents/provider-handoffs/frontend.md`.
