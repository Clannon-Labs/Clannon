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
