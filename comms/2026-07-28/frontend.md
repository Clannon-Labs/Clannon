# Frontend — 2026-07-28

- Paid-product benchmark verified **83/100**.
- Performance pass: Lighthouse 45 -> 58; LCP 6.4s -> 4.8s; TBT 1,620ms -> 750ms.
- First-value pass: truthful empty signup, guided editable brief, full mock
  signup-to-delivery Playwright journey, 390px check.
- Real API: signup, project/memory/settings, image attachment, live work,
  reload, terminal partial recovery, usage, and 390px navigation exercised.
- Recovery: workspace/reply drafts survive same-tab route/reload; live copy no
  longer claims auto-queue; long-report trust/export controls pin.
- Performance: desktop Lighthouse 95/92; mobile 63/57. A11y/BP/SEO 100.
- Gates: TypeScript, ESLint, Vitest 81/81, final mock/landing Playwright 3/3,
  real resume 1/1, production build, production dependency audit pass.
- Backend proposal: structured partial/timeout terminal semantics. Real run
  timed out after 284.3k tokens while status said delivered.
- Next: partial/preflight contract UI, mobile main-thread work, claim revision.
- completionState/completionReason UI shipped (`9dc4d84`, pushed): run-page
  "Partial" badge + reason-coded banner + "Continue this run" affordance,
  kept as a third axis from status/verificationState. tsc/eslint/vitest
  81/81/build all green. Proposal answered + archived; wake-note sent to
  backend inbox.
- Mobile main-thread reduction and claim/source targeted revision still open.
