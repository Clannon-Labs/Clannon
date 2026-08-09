# Shared provider handoff — frontend

Transfers live frontend work between Claude Code and Codex.

## Current checkpoint

- Provider: Codex
- Updated: 2026-08-09 (state-reconciliation session)
- Task: after state reconciliation, owner asked whether frontend could build without
  waiting for backend. Built missing History date filtering plus a browser-measured
  mobile overflow repair. Product changes are committed locally at current `HEAD`.
- **Identity:** this is Clannon's frontend specialist. Owns `frontend/**`, the
  paid-product UX benchmark, mock-first UI, preview evidence, and frontend API
  requests under `specification/api/requests/`. Never edits backend-owned code.
- **Live state:** `main` is at the frontend commit at `HEAD`, two commits ahead of
  `origin/main`: owner-authored `1630af0` (`backend-rust/README.md`) followed by
  this frontend work. Push deliberately withheld because pushing frontend would
  also publish the unrelated owner-authored Rust commit; owner must push/confirm
  that commit first. Worktree otherwise clean. `backend-rust/` remains owner-only.
- Seven frontend commits landed after the 2026-08-02 checkpoint below:
  templates wired (`e9c4e4a`); background-run completion notifications
  (`34192a8`); spend estimates + private-alpha signup finding (`dbc0d49`);
  searchable/filterable History (`7912eea`); print/PDF + History bulk delete +
  cold-load template crash fix (`84393a6`); PWA icon set (`7d284c9`); mock-first
  cancel/downgrade/invoices UI and HTTP contract (`6f54edb`). Reports v18-v23
  and `comms/2026-08-02/frontend.md` hold full evidence.
- Current frontend benchmark scorecard is **85.87 -> 86/100**. Its header still
  says `85.57 -> 86`, a small internal doc inconsistency to fix with the next
  benchmark-touching commit. Dominant recorded cap remains performance 64 and
  time-to-first-value 78; do not infer current causes without remeasurement.
- Built 2026-08-09: History `Any time` / `Last 7 days` / `Last 30 days` filters,
  composable with title/status. Filter changes clear bulk selection. Live 390px
  test found page width 440px from the existing flex row; `min-w-0` fixed it and
  Playwright now measures viewport equality. Benchmark honestly remains 85.87→86.
- Fresh verification: `npm run typecheck` clean, `npm run lint` clean, Vitest
  **201/201** across 26 files, production build clean, Playwright History 1/1.
  Desktop/mobile loaded captures inspected with zero console errors under
  `previews/2026-08-09_history-date-filter/`.
- Inbox: one FYI-only file,
  `proposals/to-frontend/2026-08-02_specification-directory-is-your-channel.md`;
  no ruling or reply requested. Owner-local `frontend/proposals/` is empty.
- Backend began its request sweep during this reconciliation: archive discrepancy
  is DONE/archived (false route removed); billing is IN PROGRESS; both share-link
  requests are QUEUED behind billing for security review; signup gating is BLOCKED
  on owner ruling, with backend recommending an email allowlist. These are live,
  uncommitted backend edits; do not race or edit them.
- **Recommended next product unit:** when backend's billing routes land, exercise
  existing cancel/undo/downgrade/invoices UI over real HTTP and fix only measured
  contract mismatches. Then wire share UI only after security-reviewed payload
  lands. Signup UI follows owner ruling; frontend-only gating would be security
  theater.
- Other named candidates remain lower priority: attachment reuse, account data
  export/deletion, session/device management. Notification center needs genuine
  app-wide run tracking; offline/service-worker needs an explicit live-SSE caching
  design; referral flow depends on signup-gating shape.

## Change note

Reconciled continuity against live Git because prior checkpoint stopped at billing
`e53197f`, while seven later frontend commits already reached `main`. No product
work was repeated. Fresh suite established current health; handoff now names actual
HEAD, shipped surface, open contracts, and security-first next unit.

## Previous checkpoint (2026-08-02)

- Provider: Claude Code
- Updated: 2026-08-02 (session end)
- Task: owner ordered the extreme-priority billing proposal executed, then
  asked to wrap for the day. Along the way: wrote a normal-priority proposal
  to backend on Time to First Value latency (grounded in reading
  `core/orchestrator/loop.py`/`experts/`/`models.yaml`, not speculation),
  and prepped (not yet wired in) templates/saved-workflows.
- **Real collision, resolved cleanly**: backend-coordinator dispatched a
  headless `frontend-worker` onto the exact same billing proposal, into the
  exact same working directory, concurrently with this interactive session
  — despite the proposal saying it wouldn't (my tree was already dirty).
  Caught via unexpected file changes mid-edit. Stopped touching the shared
  files immediately, waited ~40 min for the worker to exit (didn't fight it
  for the same lines), then independently verified its full output
  (`tsc`/`eslint` clean, vitest 129/129 — matched its own claimed numbers)
  before committing it as frontend's own work. Backend-coordinator had
  *also* independently reviewed and archived the proposal by the time I
  checked — two independent reviews converged on the same verdict without
  seeing each other. Commit `e53197f`, pushed clean.
- **If you're picking this up next**: watch for this pattern again. A
  proposal marked "no worker dispatched, tree is dirty" is not a guarantee
  — check `ps aux | grep crew.sh` / `.agents/runs/*.log` before assuming
  you have a file to yourself, especially on anything marked extreme
  priority (which seems to be exactly when the coordinator is most likely
  to dispatch redundantly, probably because extreme-priority items get
  swept faster).
- **Templates/saved-workflows — foundation done, UI not wired in yet**:
  `src/lib/templates.ts` (storage: brief + model overrides + projectId,
  account-wide, localStorage — NOT backend-synced, that would need a
  proposal, noted as a future upgrade not an oversight),
  `src/lib/use-templates.ts` (reactive hook, same `useSyncExternalStore`
  pattern as `use-browser-draft.ts`), `src/components/app/template-card.tsx`
  (matches the starter-example card style exactly). `src/tests/
  templates.test.ts`, 7/7 passing. Deliberately left UNCOMMITTED and NOT
  wired into `page.tsx`/`composer.tsx` — that wiring needs the now-settled
  billing composer changes as its base, and doing it concurrently with the
  billing collision would have been reckless. **Next session's first task**:
  wire the "Save as template" trigger into `Composer` (near Attach files)
  capturing brief+session.models+projectId, and render `TemplateCard`s
  alongside the starter-example cards in `page.tsx`, account-wide, per the
  owner's own scoping answers (full setup; alongside starter cards;
  account-wide for v1, per-project noted as the owner's actual preference
  if it's ever cheap to add).
- Proposal to backend on Time to First Value:
  `proposals/to-backend/2026-08-01_time-to-first-value-latency-ideas.md`
  (normal priority, not yet answered) — three grounded, falsifiable
  questions (sequential-round latency, whether progressive report streaming
  is architecturally plausible, whether research-role model tier has
  headroom), explicitly NOT asking about Performance/mobile (that's
  frontend's own framework-level problem, said so plainly).
- Two new standing `frontend/CLAUDE.md` instructions today, both owner
  instructions: don't stop at a small benchmark bump, keep proposing UX
  work unprompted, sweat small details as real product work; and the
  backend agent is a collaborator to propose real, evidenced ideas to, not
  only a dependency to escalate to when blocked.
- Verification (billing work): independently ran `tsc --noEmit`, `eslint`,
  full `vitest run` myself rather than trusting the worker's own report —
  129/129, clean, matched exactly. Spot-checked `composer.tsx`'s diff
  (extends this session's earlier `budgetExhausted` work with a *reactive*
  402-triggered block, doesn't replace it),
  `budget-exhausted-notice.tsx` (real action buttons from the structured
  402 detail), and the settings-page atomic-enforcement-claim removal, all
  good. Reviewed the worker's own live preview captures
  (`previews/2026-08-01_fixed-billing-contract/`) against a real backend
  account — genuine evidence, not fabricated.
- Full detail of the collision + billing review:
  `comms/2026-08-02/frontend.md`. Yesterday's Pass 6/7/8 benchmark work
  (84.16 → 85.29) and the failed/quota-state closure:
  `comms/2026-08-01/frontend.md`,
  `reports/frontend/frontend_report_v13.md` through `v17.md`.

## Change note

The collision is the thing worth remembering, not the billing feature
itself: a proposal explicitly stating "no worker will be dispatched because
the tree is dirty" was wrong by the time I got to it — coordination state
described in a proposal's text is a snapshot, not a guarantee, and the only
reliable check is looking at what's actually running (`ps aux`,
`.agents/runs/`) before assuming exclusive ownership of a file. The
recovery worked because the response to "someone else might be writing
this" was to stop and verify, not to assume and continue — same shape as
the `git checkout --` lesson from earlier today (v17), different mistake,
same fix: check before you trust your own model of the current state.

## Previous checkpoint (2026-08-01, fourth update)

- Provider: Claude Code
- Updated: 2026-08-01 (fourth update, same session)
- Task: owner ordered three things — (1) failed/quota-exceeded mock states,
  (2) templates/saved workflows next, (3) add a standing CLAUDE.md
  instruction to keep proposing UX work unprompted and sweat small details
  instead of stopping at a small benchmark bump.
- (3) done first (cheap, durable): "Never Stop At A Small Win" section
  added to `frontend/CLAUDE.md`.
- (1) done: two new mock QA triggers (`status:"failed"`,
  `completionReason:"rate_limit"` for quota-exceeded's mid-run form) close
  gate-95's last two untested states. Went further into PRE-run quota
  exhaustion too (the more literal "quota-exceeded" reading) since it was
  directly implied and testing (1) surfaced it: the composer had zero
  awareness of an exhausted budget even though the sidebar's own card did.
  Added `useBudgetExhausted()` (hooks.ts) + a `budgetExhausted` prop on
  `Composer`, wired at both call sites — Send disables, Enter stops
  submitting, calm inline message + upgrade link, typing never blocked.
- Read `backend/api/billing.py`'s `admit_run`: real backend already
  enforces budget server-side correctly (structured 402, no proposal
  needed) — but `http.ts`'s `errorMessage()` couldn't parse that nested
  structured body at all, silently falling back to generic text. Fixed the
  parser (`errorCode()` too — was reading from the wrong place). Added the
  same admission check to mock's `createRun` for parity.
- **Mistake, self-caught, no data lost**: while hand-writing a mutation
  check for a new test, `git checkout --` on `composer.tsx` to undo one
  deliberate line discarded the WHOLE uncommitted feature — checkout
  doesn't know intent, only HEAD. Caught within one command (grepped for
  `budgetExhausted`, found nothing), reconstructed the exact diff from this
  conversation's own record, re-verified everything before continuing.
  **`git checkout --` is retired from this workflow except on a file with
  zero uncommitted work worth losing** — use a targeted revert or stash
  instead, always.
- Verification: `tsc`/`eslint` clean, vitest 109/109 (new
  `composer.test.tsx` — 4 tests, one is a same-file sanity check proving
  Enter-to-submit is reachable in this test harness at all before trusting
  a test that asserts it's blocked, since `isFinePointer()` reads
  `matchMedia` which the global test setup always stubs `false`; and
  `http-error-parsing.test.ts` — 2 tests). Full mock-mode e2e (production
  build, port 3100, exact launch PID recorded to a scratch file and killed
  precisely — no `pkill -f` pattern anywhere this round):
  `completion-status.spec.ts` 5/5 (both new tests), `first-value.spec.ts`
  2/2 unaffected. `prior-turns.test.tsx` needed 6 tests fixed to actually
  log in first — they'd been constructing an unauthenticated `MockClient`
  whose seeded demo data (~599k tokens) was already over the unauthenticated
  default's free 100k budget, an inconsistency the missing admission check
  had been silently papering over.
- **Not done, said so plainly**: no live click-through of the
  budget-exhausted composer state specifically — reaching real exhaustion
  needs either a live account already at cap or a lot of real mock run
  time, felt disproportionate against an already-thorough unit/e2e pass.
- Commit `6da3bcd`, pushed clean. Benchmark Pass 8: failure recovery
  88->90, trust/control 91->92, **85.03 -> 85.29** (rounds to 85). Full
  detail: `reports/frontend/frontend_report_v17.md`; comms:
  `comms/2026-08-01/frontend.md`.
- **Next, not yet started**: (2) templates/saved workflows. Deliberately
  paused before building — several reasonable shapes (brief text only vs.
  brief+project+model config; a management UI to rename/edit/delete vs.
  just save-and-reuse; per-project vs. account-wide) and picking wrong
  burns real effort. Scope it with the owner (or make a clearly-reasoned
  default choice and state it) before writing code.

## Change note

Two lessons worth carrying forward. First: "test the failed state" led
naturally to "does the composer even know about budget exhaustion," which
led to a real cross-file consistency bug (sidebar knew, composer didn't) and
a real backend-response-parsing bug (structured 402 silently dropped) —
neither was the literal ask, both were directly downstream of it and worth
fixing in the same pass rather than filing separately. Second, harder-won:
`git checkout --` is not a safe way to undo a small experimental edit when
there's real uncommitted work in the same file — it reverts to HEAD, full
stop, with no concept of "just that one line." Diff first, or use a scoped
tool, before ever running it again on a file with anything worth keeping.

## Previous checkpoint (same day, earlier still — third update)

- Provider: Claude Code
- Updated: 2026-08-01 (later still, same session — third update)
- Task: owner asked to (1) browser-test v15's redesign myself, (2) continue
  the benchmark, (3) propose UX ideas and act on the one picked.
- (1) Live click-through against real backend: singular dialog confirmed
  (the v15 shared-dialog fix holds), CTA zero-projects gating confirmed,
  dialog resolves as `role="dialog"` with a real name via the accessibility
  tree (the v15 `aria-labelledby` fix, verified for real).
- (2) Wrote up 3 sessions of already-shipped, unscored work as
  `benchmark/PAID_PRODUCT_BENCHMARK.md` Pass 6: outcome clarity 87->89,
  trust/control 89->91, core workflow 86->87, accessibility 95->96.
  84.16 -> 84.93.
- (3) Offered 5 ranked ideas (2 known bugs — untested failed/quota mock
  states, a dialog autofocus quirk found during v15 testing; a stale
  mobile-density task; 2 real features — pin the project goal in view,
  templates/saved workflows). Owner picked goal-pinning.
- Implemented: `src/lib/project-goal.ts` (shared `GOAL_MEMORY_TITLE`
  constant + `findGoalEntry()` — no new backend field, same wiki-entry
  convention the goal/context/files feature already used). Pinned "GOAL"
  card on the workspace home screen, placed so it stays visible whether a
  brief is being typed or not (unlike the memory recap beside it, which
  recedes to a chip on purpose).
- Verified live on a mock Pro-plan account (needed wiki unlocked to set a
  goal at all): renders at rest, stays visible while typing, zero console
  errors either state. `tsc`/`eslint` clean, vitest 103/103 (new
  `src/tests/project-goal.test.ts`, 3 tests).
- **Known, flagged, not fixed**: on a near-empty project the same goal entry
  can also surface once inside `hydration-panel.tsx`'s memory recap list
  (it's a real wiki entry, competes for the recap's own 4-slot ranking).
  Didn't reach into that component's ranking logic for a small feature
  addition — it's a carefully choreographed, deliberately designed piece
  ("Second-Session Moment," UI_SPEC §7). Recedes naturally as memory
  accumulates; would take one line to exclude if the owner wants it closed
  now (`restingRecap` in `hydration-panel.tsx`).
- Benchmark Pass 7: continuity/retention 88->89. 84.93 -> **85.03 -> 85**.
- Process note: reused the port-3100 mock-server pattern from v15, but
  recorded the exact background PID this time and killed only that PID +
  its direct child at cleanup — no broad `pkill -f` anywhere this round,
  after v15's mistake. Confirmed `:3000` untouched before and after.
- Commit `edfb7ec`, pushed clean (fast-forward, no conflict). Full detail:
  `reports/frontend/frontend_report_v16.md`; comms:
  `comms/2026-08-01/frontend.md`.

## Change note

Two habits worth keeping from this pass: (1) when the owner asks for "test
it yourself," a live click-through catches things e2e alone can't — this
round it re-confirmed both v15 fixes hold under real backend conditions, not
just mock. (2) when adding a small feature that touches a carefully
choreographed existing component (here, `hydration-panel.tsx`'s recap
ranking), the discipline is to NOT reach in and special-case it — flag the
resulting overlap honestly instead. A minor visible redundancy, disclosed,
is better than an undisclosed change to a deliberately designed piece for
one new caller's convenience. Also: recording the exact PID at every
background-process launch from now on, not just after getting burned once —
the port-3100 pattern will keep recurring for e2e/build verification.

## Previous checkpoint (same day, earlier still — second update)

- Provider: Claude Code
- Updated: 2026-08-01 (later still, same session)
- Task: owner correction — the goal/context/reference-files fields (added
  moments earlier, see Previous checkpoint) had landed in TWO places: the
  New Project dialog (correct) and `FirstRunGuide`, an older flow that
  auto-showed decision/context/deliverable fields as the default home screen
  for any zero-run account, no click required. Owner: those fields belong
  behind an explicit "create project" click, never ambient. Asked one
  clarifying question (plain composer vs. composer + CTA); owner picked CTA.
- Implemented: deleted `FirstRunGuide`. Home screen is now identical for
  first-time and returning users. Added a "Start with a project" CTA gated
  on zero PROJECTS (not zero runs — caught via live testing that "zero runs"
  wrongly re-nudged an account that already had one project from the prior
  checkpoint's testing). Opens the same New Project dialog.
- **Found via e2e, not inspection**: lifting the dialog's open state into
  shared context caused BOTH `ProjectSwitcher` instances (sidebar duplicates
  its content for desktop rail vs. mobile drawer, always both mounted) to
  open their own dialog at once off one shared flag —
  `getByLabel('Project name')` resolved to 4 elements in Playwright. Fixed
  by extracting the dialog into `new-project-dialog.tsx`, mounted once in
  `AppShell` (not duplicated) instead of per-switcher-instance.
- **Found chasing that**: `components/ui/dialog.tsx` never wired an
  accessible name to the `<dialog>` element (no `aria-labelledby`) — a real,
  pre-existing a11y gap on every dialog in the app, invisible until
  something finally tried `getByRole("dialog", {name: ...})`. Fixed with
  `useId()`.
- Rewrote the 3 e2e specs that drove `FirstRunGuide`'s removed UI. Built +
  served a mock production bundle on :3100, ran `first-value.spec.ts` +
  `completion-status.spec.ts` for real — 5/5 passing. `real-backend.spec.ts`
  fixed for the same selectors, not executed (10-min timeouts, live backend
  needed — said so plainly, not claimed verified).
- **Own mistake mid-session**: `pkill -9 -f "next-server"` while cleaning up
  the :3100 test server was too broad and killed the shared `:3000` dev
  server too (running since before this session). Caught immediately via a
  failed curl, restarted in the same config, confirmed real traffic resumed
  before continuing. Repeated a milder version of the same pattern-matching
  mistake once more a few minutes later; that one didn't hit anything live,
  but that was luck, not care — said so in the report rather than only
  flagging the one with a consequence.
- Verification: `tsc`/`eslint` clean, vitest 100/100. Commit `89670fc`,
  pushed clean. Full detail: `reports/frontend/frontend_report_v15.md`;
  comms: `comms/2026-08-01/frontend.md`.

## Change note

Shared-state and shared-UI are not the same lift: sharing the OPEN FLAG
across triggers was correct (that's the whole point — one dialog, multiple
entry points), but the sidebar's desktop/mobile DOM duplication meant
sharing the DIALOG ITSELF too would have been wrong even before this bug —
it just took a globally-shared boolean to make the pre-existing duplication
observable. The fix (dialog owned by one always-single-mounted component,
open flag owned by context) is the right shape going forward: don't let a
component that might be duplicated in the DOM also own something that must
be a singleton. Separately: e2e caught two real, generically-useful bugs
(the duplication, the missing `aria-labelledby`) that unit tests and manual
click-through both missed — worth remembering when "the RTL test already
covers this" starts to feel like enough.

## Previous checkpoint (same day, earlier still)

- Provider: Claude Code
- Updated: 2026-08-01 (earlier same session)
- Task: owner asked where the benchmark stood; backend answered `:8000`
  health-check live during the conversation, so switched to real HTTP
  verification. Owner then asked about a missing project-creation
  goal/references-files flow — confirmed via git history + backend source it
  never existed (not a regression), then asked to add it anyway.
- Implemented: New Project dialog gained optional goal + reference-files
  fields alongside the existing client-context note, all three feeding the
  project's wiki via the existing `saveMemoryEntry`/`uploadMemoryFiles`
  contracts — no new endpoint.
- **Found while browser-testing this against live backend as a fresh
  free-tier signup: a real plan-tier bypass, not a frontend bug.**
  `GET /memory`, `POST /projects` (`seedFacts`), `POST /memory`, and
  `POST /memory/upload` in `backend/api/app.py` never check `user.plan`
  anywhere — a locked-tier account's wiki shows as UI-locked but the full
  content is already in the network response, and nothing stops writing to
  it either (confirmed live: 3 wiki entries written and readable via the
  count badge on an account whose plan doesn't include wiki).
- Owner's instruction on hearing this: must not be reachable "no matter
  what," must not be bypassable from the frontend, backend must enforce.
  Rewrote the fix from "warn but allow" to "don't render at all" — the three
  fields don't exist in the DOM when `!plan.memoryTiers.includes("wiki")`,
  and `submitCreate` independently zeroes them so stale state can't slip a
  write through either.
- Filed `proposals/to-backend/2026-08-01_memory-plan-tier-not-enforced-serverside.md`
  (Priority: high) covering both the read leak and all three open write
  paths — explicit that frontend's fix is UX, the real boundary is
  server-side and isn't frontend's tree to fix.
- Verification: `tsc`/`eslint` clean, vitest 100/100 (new
  `src/tests/project-switcher.test.tsx`, 3 tests — proves the field-visible
  branch, the field-absent branch, and that a locked-plan submit sends
  `seedFacts: undefined` and never calls the goal/file mutations). Live
  browser click-through against the real backend for both branches, zero
  console errors either time (used `http://192.168.18.84:3000` — plain
  `localhost` trips a CSP mismatch in this dev config, noted, not chased).
- Commit `ef76b2e`, pushed clean (fast-forward past two intervening backend
  commits, no conflict). Full detail: `reports/frontend/frontend_report_v14.md`;
  comms: `comms/2026-08-01/frontend.md`.
- One unchased loose end: a hard `page.goto` to `/app/memory` once bounced
  the session to `/login` mid-session even though `/app` survived the same
  hard-navigation pattern moments before/after. Didn't reproduce deliberately
  a second time; could be a `next dev --reload` artifact. Worth watching for,
  not confirmed as a real bug.

## Change note

Added product UX, but browser-testing it against a live backend (a first for
this session — backend hadn't been reachable earlier) surfaced that the
plan-tier "lock" this feature writes into has never been enforced
server-side, on read or write. Owner was explicit that a UI-only gate isn't
acceptable once known — rewrote from disclosure-and-allow to
absence-and-guard on the frontend side, and filed the server-side half as a
high-priority proposal rather than trying to fix `api/` myself. The backend
coming up mid-session is also why this checkpoint exists at all instead of
staying mock-only: real HTTP testing catches classes of bug (contract-level,
enforcement-level) that mock-mode and even RTL tests structurally cannot.

## Previous checkpoint (same day, earlier)

- Provider: Claude Code
- Updated: 2026-08-01 (earlier same session)
- Task: close `proposals/to-frontend/2026-07-30_memory-provenance-cards.md`
  (backend proposal: render curator provenance on Memory archive cards).
- Found mid-flight: a prior uncommitted session had already done most of it
  (types, mock fixtures, card rendering). Read the proposal's acceptance
  list against the diff line by line and found the real gap — delete was
  wiki-only in the UI even though the mock backend already allowed deleting
  any tier; confirm dialog + toast unconditionally claimed "wiki" + "undo"
  for every tier.
- Implemented: inferred tiers (semantic/episodic/procedural) are now
  deletable (owner-scoped, no edit, no undo — there's no recreate op for a
  pipeline-derived fact); wiki keeps edit + real undo. Dialog/toast copy is
  now tier-honest instead of hardcoded to wiki language.
- Verification: `tsc --noEmit` clean, `eslint` clean, full vitest 97/97
  (was 92). New `src/tests/memory-page.test.tsx` renders the real page with
  hooks doubled and asserts the DOM/interactions, not just types — added a
  `<dialog>.showModal/close` polyfill to `setup.ts` since it's the first
  test to open one. Did **not** get a real Chrome click-through: the
  `claude-in-chrome` extension wasn't connected in this environment (tried
  after the user offered their own Brave window too — same failure), and a
  second `next dev` for Playwright collided with an existing `:3000` server
  already running in `http` mode against an unreachable backend, which I
  left alone rather than kill (might have been someone's active window).
  Said this plainly in the report rather than calling it browser-verified.
- Commit `6531b29`, pushed clean to `origin/main`. Full detail:
  `reports/frontend/frontend_report_v13.md`; comms:
  `comms/2026-08-01/frontend.md`.
- Housekeeping note for whoever reads this next: this checkpoint had gone
  stale — it still said "2026-07-29 / tomorrow: mobile density" while HEAD
  had already moved through `eb48dc9`/`981c8d7` (sent-prompt revision work,
  which also archived `owner-critique.md` — confirmed archived, so that
  proposal is genuinely done, not just forgotten). The mobile-density task
  below is preserved as-is since I found no commit that clearly closes it —
  worth confirming its real status before resuming it blind.

## Change note

Genuine gap between "types/mock/rendering done" and "acceptance criteria
met" — the proposal explicitly required inferred-tier delete, and it was
easy to read the uncommitted diff as finished without checking that one
line item. Also restored handoff continuity: the file had gone three
sessions stale (still dated 2026-07-29) while real work landed on top of
it, so the mobile-density task and the owner-critique proposal status below
needed a fresh read against `git log`, not a trust of what this file said.

## Previous checkpoint

- Provider: Codex
- Updated: 2026-07-29
- Task: owner phone-density critique + instant first-response app shell;
  preserve exact continuation for tomorrow
- Implemented now: `/app` auth wait no longer shows a blank full-screen logo.
  Server-rendered `WorkspaceLoadingShell` arrives as `RequireAuth`'s fallback,
  matching real desktop rail/mobile header, content cards, and composer
  geometry. Static server component is passed into client gate as rendered
  children, so no fake sidebar interactions or account/project data join
  initial client bundle. Route `loading.tsx` reuses same content skeleton.
- First-response evidence: dev `/app` HTML is 54,104 raw bytes and ~9,117 bytes
  under gzip-9, below owner's ~14 KB initial-window target. This is directional,
  not a production wire guarantee; CDN/compression/TLS deployment must be
  measured after hosting. Desktop/mobile previews:
  `frontend/previews/2026-07-29_initial-shell/`.
- Verification: TypeScript, zero-warning ESLint, Vitest 92/92, isolated Next
  production build, 1440x900 and 390x844 browser review.
- Tomorrow TOP frontend task (status unconfirmed as of 2026-08-01 — see
  Change note above): full mobile density pass, not blanket font shrinking.
  Current marketing page measures 9,604 px tall at 390 px and stacks nearly
  every desktop card vertically (starter examples, five pipeline stages,
  four memory tiers, four pricing plans). Audit 320/360/390/430 widths;
  restore breathing room through progressive disclosure, horizontal
  snap/peek where discoverable, section pacing, and fewer simultaneous
  choices. Preserve tap targets, accessibility, and desktop information.
- Proposal review: `proposals/to-frontend/owner-critique.md` — CONFIRMED
  archived as of 2026-08-01 (`eb48dc9`/`981c8d7` landed the sent-prompt
  revision work this was waiting on). No longer open.
- Honest benchmark: was 84.16 as of this checkpoint; not re-measured since.

## Older checkpoint

- Provider: Codex
- Updated: 2026-07-29
- Task: fix Dependabot alert 21, `brace-expansion` OOM DoS in frontend lockfile
- State: fixed with official `brace-expansion@1.1.17` 1.x security backport;
  override floor raised and lockfile regenerated. Dependency is dev-only under
  `eslint -> minimatch@3`, not shipped application runtime.
- Evidence: clean fresh `npm ci` resolves 1.1.17; exact regression probe with
  1,500 chained brace groups and `maxLength: 100000` returns 99,000 total
  characters instead of unbounded allocation. Production audit reports zero.
- Verification: TypeScript, zero-warning ESLint, Vitest 92/92, `npm ls`, fresh
  lock install, security regression probe.
- Advisory caveat: GitHub/npm advisory metadata still lists only 5.0.8 as
  patched and therefore may keep alert/audit red temporarily. Upstream tag
  `v1.1.17` explicitly backports GHSA-mh99-v99m-4gvg and contains its bounds.
- Honest benchmark: remains 84.16; dependency security maintenance, no scored
  journey change.

## Change note

Dependabot finding was real but development-only. Avoided incompatible forced
upgrade from CommonJS `brace-expansion@1` to changed v5 API. Used official v1
backport released today, then proved both fresh-install resolution and actual
memory bound rather than trusting version metadata alone.

## Previous checkpoint

- Provider: Codex
- Updated: 2026-07-29
- Task: choose between two owner-supplied logo candidates, split chosen sheet,
  and deploy each variant where it fits
- Choice: `Clannon_latest_logo.png`; stronger, more ownable system than generic
  purple C, and monochrome treatment fits existing product palette
- Built: pixel-preserving crops under `assets/brand/` — primary lockup
  1027x291, symbol 305x298, reversed/dark 491x461. Sheet background alone made
  transparent; no resampling. Exact copies live in `frontend/public/brand/`.
- Placement: primary lockup drives every `Wordmark`; symbol drives every `Mark`
  plus a dark app icon; reversed lockup drives generated Open Graph image.
  Explicit root-theme inversion keeps monochrome assets readable in dark mode.
- Verification: TypeScript, zero-warning ESLint, Vitest 92/92, isolated Next
  production build, root/public asset byte comparison, desktop/light,
  desktop/dark, mobile/dark, and 1200x630 social-card visual review. Evidence:
  `frontend/previews/2026-07-29_logo-refresh/`.
- Honest benchmark: remains 84.16. Brand replacement improves identity
  consistency but does not close a scored product-journey gap.
- Worktree: preserve unrelated backend/root/frontend launcher changes. The
  unused `assets/Clannon Labs.png` candidate remains an untracked owner input;
  chosen sheet is retained as `assets/brand/clannon-logo-source-sheet.png`.

## Change note

Owner supplied two logo directions. Latest sheet won on distinctiveness and
fit. Crops preserve source pixels; frontend now uses one-door brand config,
appropriate per-surface variants, and a legible dark treatment instead of
forcing one raster into every context.

## Previous checkpoint

- Provider: Codex
- Updated: 2026-07-29
- Task: owner critique — sent prompts need stable Copy/Edit actions; editing an
  earlier turn must restart from its prefix and exclude later turns from context
- State: frontend implementation complete, mock/browser-proven, committed and
  pushed as `eb48dc9`; real HTTP completion BLOCKED on backend proposal
  `proposals/to-backend/2026-07-29_revise-turn-branch-contract.md`
- Built: `TurnPrompt` (desktop hover/focus, mobile tap, inline prefilled edit,
  explicit context cut), Clipboard API + insecure-LAN fallback, revise client/
  hook/http/mock contract, real mock lineage branching, removed failed-callout
  fake edit button
- Verification: TypeScript, ESLint, Vitest 92/92, isolated production build;
  Playwright desktop revision 1/1 and 390px tap 1/1. Evidence:
  `previews/2026-07-29_prompt-revision/`; detail:
  `reports/frontend/frontend_report_v12.md`
- Honest benchmark: remains 84.16. Do not raise until backend endpoint lands
  and a real HTTP revision proves later turns are absent while saved memory is
  still eligible.
- Owner proposal `proposals/to-frontend/owner-critique.md` remains accepted,
  not done, until that live proof.
- Owner clarified LAW 2 for frontend: 500 lines is a readability signal, not a
  hard split mandate. Keep cohesive component/state/interaction families
  together when that reads better; split real responsibility bloat. Durable
  rule now lives in `frontend/CLAUDE.md`.

## Change note

Owner's screenshot exposed a functionality defect, not polish: callout-local
“Edit and resubmit” never edited anything. Frontend now treats prompt actions
as part of the prompt in every outcome state. Branch semantics cannot be faked
with follow-up; durable backend proposal carries exact contract.

## Previous checkpoint

- Provider: Codex
- Updated: 2026-07-29
- Task: persist owner clarification that this role must interpret broad or
  ambiguous questions as frontend questions first
- State: done in `frontend/CLAUDE.md` under `Frontend-First Interpretation`
- Standing interpretation: lead with frontend product, frontend benchmark,
  frontend backlog, and user experience. Backend context is optional,
  secondary, and brief unless owner explicitly asks for backend or
  cross-cutting system work.
- Code/product state unchanged. Prior implementation checkpoint follows.

## Change note

Owner corrected a role-context failure: a broad benchmark question was answered
backend-first even though this is the frontend agent. Frontend-first
interpretation is now durable in the module charter rather than left only in
conversation history.

## Previous checkpoint

- Provider: Claude Code
- Updated: 2026-07-28 (later in the day than the checkpoint below)
- Task: owner instruction to stop auditing from code/screenshots and
  actually be the user — sign up cold, use the real product end to end via
  real Chrome (chrome-devtools MCP, not the Playwright test browser), fix
  what a first-time non-technical user would actually hit
- State: done, pushed — `95eb6f0` (on top of everything in the prior
  checkpoint below). Full accounting: `reports/frontend/frontend_report_v11.md`.
- Two real bugs found by using the product, not reading it, both fixed in
  `8ef1036`:
  1. A fresh signup's "empty account" promise didn't survive a page reload.
     `MockClient`'s class field initializers (`private projects =
     structuredClone(SEED_PROJECTS)` etc.) re-seed on every full page load
     since it's a client-side singleton reconstructed from scratch each
     navigation — the earlier empty-signup fix only ever cleared the
     current in-memory instance. Confirmed live: sign up, click into the
     memory page, watch a stranger's "Meridian Skincare" project and
     599k/6M usage appear. Fixed with a persisted `EMPTY_ACCOUNT_KEY` flag
     the constructor checks, `login()`/`loginWithProvider()` explicitly
     reseeding the live instance too (caught during testing: flipping the
     flag alone doesn't help a login immediately after a signup, since
     that instance is already constructed empty).
  2. First-time signups were told "Welcome back" (no first-run branch in
     the greeting pool). Fixed with plain "Welcome" — advisor review caught
     a loading-state race in the first attempt (`isFirstRun` is false while
     `runs` is still in flight, and the greeting renders outside the
     loading gate) before it shipped; gated on `!workspaceReady` too.
  3. Incidental: every normal mock delivery now sets `verificationState:
     "grounded"`, not just the QA trigger — the VERIFIED seal was silently
     absent from every ordinary run before this.
- Checked and deliberately left alone: decision-log jargon (already
  opt-in, auto-collapses ~2.2s after delivery); Settings/Usage/Billing under
  the account menu, not main nav (matches Slack/Notion/ChatGPT convention);
  Models settings page (already plain-language with good defaults).
- Score: 83.42 -> 84.16/100. Outcome clarity 85->87, trust/control 87->89,
  continuity 86->88 — each tied to one of the two bugs above with browser
  evidence in `previews/2026-07-28_be-the-user-pass/`. **Stated the 90-gate
  performance blocker explicitly at the top of `PAID_PRODUCT_BENCHMARK.md`**
  (mobile Lighthouse floor is Next.js App Router's own hydration runtime,
  proven in the prior checkpoint's Pass 3, not reachable by another UX
  pass) so the next session doesn't re-derive it or chase the number past
  what the evidence supports.
- Verification: tsc/eslint/vitest 87/87/build green. Playwright regression
  check (`first-value.spec.ts`, `landing.spec.ts`, `completion-status.spec.ts`)
  5/6 green in one run; the 6th (blocked-run case) failed once under
  back-to-back load, then passed both standalone and in isolation right
  after — confirmed a pre-existing sequencing flake, not a regression, by
  actually re-running it rather than assuming.
- Not done: `failed`/quota-exceeded mock states still untested (same
  bounded pattern would close them). Performance needs the dedicated
  framework-level session already flagged in the prior checkpoint — nothing
  new to add there.

## Change note

Owner said to stop reasoning about the product from code and screenshots and
actually use it cold, as a non-technical first-timer would. That surfaced
two real bugs no amount of code review had caught (data leaking into a
fresh account across a reload; a first-timer told "welcome back") — the kind
of thing that only shows up by clicking through, not by reading the diff
that claimed to fix it the first time. Consulted advisor before committing
and it caught a real defect in my own fix (a loading-state race) before it
shipped, not after.

## Previous checkpoint

- Provider: Claude Code
- Updated: 2026-07-28 (earlier the same day than the checkpoint above)
- Task: land the stranded worktree from the prior checkpoint, then push the
  paid-product benchmark genuinely past 83 (owner instruction, that session)
- State: done through four commits, all pushed —
  `e1beca8`/`d4e35ec` (landed the stranded worktree), `92d940d` (extracted +
  tested `completion-status.tsx`), `e1535ff` (browser-verified both the
  completion-status UI and the pre-existing filter-block UI for the first
  time). Full accounting: `reports/frontend/frontend_report_v9.md`,
  `frontend_report_v10.md`.
- The stranded worktree (prior checkpoint's "STILL UNCOMMITTED") is landed:
  re-verified independently first (tsc/eslint/vitest 81/81/build), then a
  real Playwright pass caught a self-inflicted stale-chunk error (rebuilt
  `next build` without restarting `next start` — not a product bug, hit it
  twice that session, both times run to ground with a raw Playwright +
  `console.log` script rather than assumed-away). Excluded
  `.agents/provider-handoffs/release.md` and `comms/2026-07-27/release.md`
  from every commit — release role's own files in the same shared tree.
- Score: 82.61 -> 83.42/100, still rounded to 83. New evidence: added two
  QA-only mock triggers (`src/lib/api/mock.ts`, keyed off brief text, never
  surfaced as a suggestion) since `MockClient` never simulated a
  `blocked`/`partial` terminal — closed that gap, drove both with real
  Playwright + Chrome at desktop and 390px
  (`previews/2026-07-28_completion-status/`). Outcome clarity 83->85,
  failure recovery 85->88, trust/control 86->87, core workflow 85->86, each
  tied to the new evidence. Performance re-measured 3x (Pass 3), honestly
  held at 64 — traced the mobile TBT floor to Next.js App Router's own
  hydration/RSC runtime (verified no react-query/motion in that chunk, and
  every marketing component is already a server component) — a framework
  floor, not an app bug, needs a dedicated session to attack further.
- Real backend (`localhost:8000`) refused connection all session — no
  re-verification of the real-journey timeout finding was possible; noted
  honestly rather than reused as if still current.
- Change note: landed the previous checkpoint's stranded 83/100 worktree
  (was "STILL UNCOMMITTED" for two checkpoints running) rather than leaving
  it stranded a third time. Then answered "push toward 85+ genuinely" by
  closing a real, named gap (completion-status UI had zero browser
  evidence) instead of inflating the number — landed at 83.42, said so
  plainly, and left performance/backend-timing honestly unmoved where the
  evidence didn't support a claim either way.

## Previous checkpoint

- Provider: Codex
- Updated: 2026-07-28
- Task: raise paid-product frontend benchmark genuinely above 80
- State: verified 83/100; real journey/performance pass complete in uncommitted
  shared worktree
- Evidence: `frontend/benchmark/REAL_JOURNEY.md`,
  `frontend/benchmark/PERFORMANCE.md`, `reports/frontend/frontend_report_v8.md`,
  dated real-backend/performance previews
- Browser proof: real signup -> project/memory/settings -> restored brief ->
  image attachment -> live/reload -> terminal partial recovery; real 390px
  signup/navigation; keyboard/theme landing behavior
- Verification: TypeScript, ESLint, 81/81 Vitest, final mock/landing Playwright
  3/3, real resume 1/1, production build, production dependency audit all pass
- Performance: desktop Lighthouse 95/92; mobile 63/57, so 90 gate still fails
- Backend finding: real run used 284.3k tokens, timed out, but status said
  delivered. Proposal:
  `proposals/to-backend/2026-07-28_partial-timeout-terminal-contract.md`
- Next frontend value: structured partial UI/preflight time-spend, mobile
  main-thread reduction, then claim/source/targeted revision
- Worktree warning: unrelated backend/release/root edits exist; preserve them
- Change note: Codex completed real API journey and second performance/recovery
  pass. Score moved 80 -> 83. Backend environment was used, proposal answered,
  real partial timeout recorded, workspace/reply drafts hardened, live copy
  corrected, long-report controls pinned, marketing interactions moved
  server-side. STILL UNCOMMITTED as of the next (Claude Code) checkpoint above
  — its huge dirty-tree footprint is the "worktree note" flagged there; not
  evaluated or committed by that session, still needs its owner.

## Previous checkpoint

- Provider: not recorded
- Updated: 2026-07-26
- Task: read `frontend/HANDOFF.md`, frontend charter, inboxes, latest reports,
  Git state
- State: dual-provider supervisor installed; no provider switch had occurred
- Next: resume latest provider-native session and continue durable frontend state
- Files touched: see Git status; never assume dirty files belong to this provider
- Verification: supervisor scripts passed Bash syntax, ShellCheck, and diff checks
- Change note: created for cross-provider continuity; no earlier checkpoint
  existed and `frontend/HANDOFF.md` remained authoritative for older history
