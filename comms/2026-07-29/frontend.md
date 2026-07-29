# Frontend — 2026-07-29

## 21:00 — sent-prompt revision frontend complete; backend contract needed

Owner's top critique verified: failed-run “Edit and resubmit” only focused an
empty composer, successful turns had no edit, and no API could cut descendants
from context.

Frontend now owns Copy/Edit on every sent prompt (desktop hover/focus, mobile
tap), inline prefilled revision, explicit branch/memory copy, and mock-proven
prefix-only branch behavior. TypeScript, ESLint, Vitest 92/92, production build,
desktop + 390px browser proof green.

@backend — high-priority contract proposal:
`proposals/to-backend/2026-07-29_revise-turn-branch-contract.md`. Need
`POST /runs/:id/revise` before real HTTP flow is complete. Frontend adapter is
ready; no benchmark score increase claimed.

## 22:40 — owner-selected logo system deployed

Chose `Clannon_latest_logo.png` over purple C: more ownable symbol, complete
lockup system, better fit with current monochrome/green product.

Split source sheet without resampling into primary, symbol, and reversed/dark
assets. Primary now owns wordmark surfaces; symbol owns UI marks and app icon;
reversed lockup owns social card. Dark-mode inversion follows Clannon's explicit
root theme class. TypeScript, zero-warning ESLint, Vitest 92/92, isolated
production build, byte comparison, and desktop/mobile visual review green.
Benchmark stays 84.16; identity improvement does not close a scored journey gap.

## 22:50 — Dependabot OOM alert fixed

Dependabot 21 traced to dev-only `eslint -> minimatch@3 -> brace-expansion`.
Raised override floor from 1.1.16 to official 1.1.17 security backport and
regenerated lockfile. Fresh `npm ci` resolves patched version; 1,500-group
regression probe stays under 100,000-character budget. Production audit zero;
TypeScript, ESLint, Vitest 92/92 green.

GitHub advisory metadata still names only 5.0.8 as patched, so alert closure may
lag even though upstream 1.1.17 explicitly backports GHSA-mh99-v99m-4gvg.
