# Shared provider handoff — frontend

Transfers live frontend work between Claude Code and Codex.

## Current checkpoint

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
