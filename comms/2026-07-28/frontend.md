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
- Landed the stranded Codex worktree (`e1beca8`, `d4e35ec`): truthful empty
  signup, first-run-guide, workspace/reply drafts, theme boot script inlined,
  Providers scoped out of marketing routes, Playwright e2e suite,
  benchmark/ evidence docs. Re-verified independently before committing —
  tsc/eslint/vitest 81/81/build green, then a real Playwright pass caught a
  self-inflicted stale-chunk error (rebuilt without restarting the server,
  not a real bug — see report v9), fixed, re-verified clean.
- Extracted completion-status.tsx out of the run page into its own tested
  component (`92d940d`), 6 new unit tests, 87/87.
- Browser-verified completionState UI + the pre-existing filter-block UI for
  the first time (`e1535ff`): added two QA-only mock triggers (never
  surfaced as a suggestion) since MockClient never simulated blocked/partial
  before, drove both with real Playwright + Chrome at desktop and 390px.
  Screenshots in `previews/2026-07-28_completion-status/`.
- Score: 82.61 -> 83.42/100, still rounds to 83 (outcome clarity 83->85,
  failure recovery 85->88, trust/control 86->87, core workflow 85->86 — each
  tied to the new browser evidence). Performance re-measured 3x (Pass 3),
  honestly held at 64 — traced the TBT floor to Next.js App Router's own
  hydration runtime, not app code; not claiming a change without stronger
  evidence either way. Full accounting: reports/frontend/frontend_report_v9.md,
  frontend_report_v10.md.
- Real backend (`localhost:8000`) unreachable this session — no re-verification
  of the timeout/partial real-journey finding was possible.
- Next: performance needs a dedicated session if it's to move past 64 (App
  Router framework floor, not a quick fix); `failed`/quota states still
  untested (same bounded mock-trigger + Playwright pattern would close them).
- Owner instruction: stop auditing from code, actually be the user. Signed up
  cold via chrome-devtools MCP (real Chrome, not the Playwright harness),
  used the real product end to end. Found two real bugs (`8ef1036`, pushed):
  (1) fresh signup's "empty account" promise didn't survive a page reload —
  MockClient's class fields re-seeded demo "Meridian Skincare" data on every
  navigation, only the in-memory instance was ever actually cleared. Fixed
  with a persisted empty-account flag + explicit reseed on login (a login
  right after signup was staying empty — caught before shipping). (2)
  first-time signups were told "Welcome back" — no first-run branch in the
  greeting pool; advisor review caught a loading-state race in my first fix
  before it shipped. Also: every normal delivered run now shows the VERIFIED
  seal (was silently absent except on my QA test scenario).
- Checked and left alone: decision-log jargon already auto-collapses and is
  opt-in; Settings/Usage/Billing live under the account menu (matches
  Slack/Notion/ChatGPT convention, not a gap); Models settings already
  plain-language with good defaults.
- Score: 83.42 -> 84.16/100 (outcome clarity 85->87, trust/control 87->89,
  continuity 86->88 — each tied to one of the two bugs). Stated the 90-gate
  performance blocker explicitly at the top of PAID_PRODUCT_BENCHMARK.md so
  it isn't re-derived or chased past what Pass 3 already proved. Full
  accounting: reports/frontend/frontend_report_v11.md.
- Verification: tsc/eslint/vitest 87/87/build green; Playwright 5/6 in one
  run, 6th confirmed a pre-existing sequencing flake (not a regression) by
  isolated re-run before moving on.
