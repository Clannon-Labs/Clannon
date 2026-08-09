# frontend — 2026-08-09

## History date filtering shipped; browser pass caught mobile overflow

Owner asked whether frontend had useful work independent of backend. Yes: Pass 11's
own History gap still named date filtering, while shipped page only had title search
and status filtering.

Built `Any time` / `Last 7 days` / `Last 30 days` from existing run timestamps. Filters
compose with title/status; changing a filter clears bulk selection so hidden rows cannot
remain selected for deletion. No API change.

Real 390px production-browser pass found loaded History rows widened page to 440px.
Cause: flex link kept min-content width beside checkbox/status badge. Fixed with
`min-w-0`; Playwright now asserts document width equals 390px after login, load, and
date selection.

Verification: TypeScript clean, ESLint clean, Vitest 201/201, production build,
Playwright 1/1. Desktop/mobile captures inspected, zero console errors:
`frontend/previews/2026-08-09_history-date-filter/`.

No benchmark inflation: 85.87 → 86 remains. Date filter completes Pass 11's same
continuity surface; another point would double-count it. Benchmark header's stale
85.57 was corrected to 85.87.
