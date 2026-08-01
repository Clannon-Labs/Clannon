# Shared provider handoff — frontend

Transfers live frontend work between Claude Code and Codex.

## Current checkpoint

- Provider: Claude Code
- Updated: 2026-08-01
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
