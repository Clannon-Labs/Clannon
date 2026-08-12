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

---

## Update: F-01 build-phase bypass closed (later same day)

Independent `frontend-audit` report_v3 retested the F-01 fix above against pushed
`adea99a` and found a narrow bypass: `NEXT_PUBLIC_API_MODE=mock next build
--debug-prerender` exits 0 and produces a deployable build wired to `MockClient`,
because that flag makes Turbopack inline `NODE_ENV` as `"development"` in compiled
chunks, and the guard's `nodeEnv` check reads exactly that inlined value. Dispatched
again via `proposals/to-frontend/2026-08-12_close-debug-prerender-mock-bypass.md`.

Verified the exact reproduction myself first (matched report_v3: normal build exit 1,
`--debug-prerender` build exit 0 with mock chunks present). Root cause confirmed by
reading Next's installed CLI/build source and by empirical probes: the `phase`
argument Next passes to a function-form `next.config.ts`, and `process.env.NEXT_PHASE`
set during page-data collection, are both `"phase-production-build"` for every
`next build` — with or without `--debug-prerender`. Only NODE_ENV is steerable by that
flag; phase is not.

Fix: new `src/config/api-mode.ts` — one pure `resolveApiMode(value, phase)` gating on
`phase === PHASE_PRODUCTION_BUILD` (from `next/constants`). `next.config.ts` now
exports the phase-aware function form and calls it with Next's real `phase` argument
at config load (throws before Turbopack starts — the authoritative, unbypassable
gate). `app.config.ts` calls the same function with `process.env.NEXT_PHASE` as
defense-in-depth. Old NODE_ENV-based logic and its false comment are gone.

Verified with real commands: `mock` + plain `next build` → exit 1; `mock` +
`--debug-prerender` → **exit 1 now** (was 0, bypass closed); `http` build → exit 0;
unset mode → exit 0; `mock` + `next dev` → boots clean. `vitest run` 274/274 (added one
regression test proving the gate survives an ambient/inlined `NODE_ENV=development`
alongside the real build phase); `tsc --noEmit` clean; `eslint .` clean.

Only owned files touched: `next.config.ts`, `src/config/api-mode.ts` (new),
`src/config/app.config.ts`, `src/tests/app-config-security.test.ts`. F-02, CSP,
backend, dependencies, UX, CI untouched. No visual change, no screenshots. Left
uncommitted per dispatch mandate.
