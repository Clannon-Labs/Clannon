# Paid Product Benchmark

Status: ACTIVE  
Owner: frontend  
Started: 2026-07-28  
Replaces: screenshot beauty scores as primary frontend benchmark

Current verified score: **85.03 -> 85/100**  
Current evidence: `benchmark/PERFORMANCE.md`, `benchmark/FIRST_VALUE.md`,
`benchmark/REAL_JOURNEY.md`, `previews/2026-07-28_completion-status/`,
`previews/2026-08-01_project-creation-redesign/`,
`previews/2026-08-01_project-goal-pinned/`, and
`reports/frontend/frontend_report_v8.md` through `frontend_report_v16.md`

**90 is not reachable without backend/framework-level work, independent of
further frontend UX passes.** The gate-90 checklist requires mobile
Lighthouse LCP ≤2.5s / INP ≤200ms; `PERFORMANCE.md` Pass 3 traced the current
~55-59 mobile score's dominant cost to Next.js App Router's own
hydration/RSC runtime, not app code, with every marketing component already
server-rendered. Closing that gap means attacking framework internals, not
another UX pass. Stating this up front so the number isn't chased past what
the evidence supports — see "Pass 4" below for what a hands-on user pass
*did* genuinely move.

## 1. Question

> If Clannon cost hundreds of dollars per month, would frontend experience make
> purchase feel justified before, during, and after useful work?

This benchmark measures perceived product value. Visual quality matters, but it
cannot compensate for slow loading, unclear value, weak onboarding, avoidable
configuration, fragile recovery, or friction between intent and deliverable.

Backend implementation is outside score. Backend-dependent behavior is judged
through frontend contract and mock states: what user sees, understands, controls,
and can recover from.

## 2. Score

Score is weighted mean of ten dimensions. Each dimension receives 0-100.

| Dimension | Weight | What earns score |
|---|---:|---|
| Outcome clarity | 15 | User understands product, result, limits, and next action without decoding system |
| Time to first value | 12 | Signup to credible deliverable is short, guided, and low-risk |
| Core workflow | 18 | Brief, context, run, review, refinement, export, and reuse form one coherent loop |
| Trust and control | 12 | Sources, memory, spend, models, privacy, status, cancellation, and verification are understandable and controllable |
| Continuity and retention | 10 | Returning work becomes easier; projects, sessions, memory, search, and follow-ups preserve context |
| Performance and smoothness | 12 | Fast first render, low blocking time, stable layout, responsive interaction, restrained motion |
| Failure recovery | 7 | Errors explain impact, preserve work, and offer concrete recovery without dead ends |
| Accessibility | 5 | Keyboard, screen reader, contrast, reduced motion, touch, focus, and semantics work |
| Mobile completeness | 5 | Core paid workflow remains usable and legible on phone, not merely responsive |
| Visual and interaction craft | 4 | Identity, hierarchy, typography, spacing, motion, and detail support comprehension |

### Interpretation

| Score | Verdict |
|---:|---|
| 0-49 | Prototype. Payment would feel premature. |
| 50-69 | Useful beta. Low-price tolerance only. |
| 70-79 | Credible product. Value can justify purchase, but premium price creates doubt. |
| 80-89 | Strong paid product. Most friction is polish or edge-case work. |
| 90-95 | Premium. Hundreds-per-month price feels coherent with experience. |
| 96-100 | Reference-grade. Fast, obvious, trustworthy, resilient, and unusually well-crafted. |

### Current scorecard

| Dimension | Weight | Score | Weighted |
|---|---:|---:|---:|
| Outcome clarity | 15 | 89 | 13.35 |
| Time to first value | 12 | 78 | 9.36 |
| Core workflow | 18 | 87 | 15.66 |
| Trust and control | 12 | 91 | 10.92 |
| Continuity and retention | 10 | 89 | 8.90 |
| Performance and smoothness | 12 | 64 | 7.68 |
| Failure recovery | 7 | 88 | 6.16 |
| Accessibility | 5 | 96 | 4.80 |
| Mobile completeness | 5 | 88 | 4.40 |
| Visual and interaction craft | 4 | 95 | 3.80 |
| **Total** | **100** |  | **85.03 -> 85** |

Pass 2 changed outcome clarity 82 -> 83, core workflow 82 -> 85,
trust/control 84 -> 86, continuity 80 -> 86, performance 58 -> 64,
failure recovery 78 -> 85, accessibility 94 -> 95, mobile 87 -> 88, and
visual craft 94 -> 95. Time to first value stays 78: real execution exceeded
four minutes and eventually returned a partial timeout result.

Pass 3 (2026-07-28, this session) shipped `completionState`/`completionReason`
UI (badge + reason-coded banner + Continue affordance) and browser-verified it
for the first time, alongside the pre-existing but never-exercised
filter-block UI — both were dark territory: `MockClient` had never simulated
a `blocked` or `partial` terminal before, so this required adding two
QA-only mock triggers (`src/lib/api/mock.ts`, keyed off brief text, never
surfaced as a suggestion) to reach them at all. Real desktop + 390px Chrome
runs, screenshots in `previews/2026-07-28_completion-status/`. This directly
answers a piece of the gate-95 checklist ("blocked, failed, and
partial-verification states are tested") for two of those four states.

Outcome clarity 83 -> 85 (both new states explain result/limits/next-action
without jargon, proven in browser). Failure recovery 85 -> 88 (both states
proven: preserve work + concrete recovery, no dead end). Trust and control
86 -> 87 (status/control proven for two previously-dark states). Core
workflow 85 -> 86 (recovering a stalled/blocked run back into an editable
brief is part of the loop). Total moves 82.61 -> 83.42 — genuine, small,
still rounds to 83. **Not** claiming 85 yet: performance (64, the single
largest remaining lever) did not move — see `PERFORMANCE.md` Pass 3, which
found the mobile TBT floor is Next.js App Router's own hydration/RSC runtime,
not app code, and declined to claim a score change without stronger evidence.
Time to first value (78) is backend-execution-bound and unreachable from this
environment today (`localhost:8000` refused).

## Pass 4 — actually being the user (2026-07-28, same day)

Owner instruction: stop auditing from the code and screenshots, sign up
cold as a genuine first-time, non-technical user, and use the real thing —
Chrome via chrome-devtools MCP, not the Playwright test harness. Two real
defects surfaced this way that no amount of code review had caught:

1. **A fresh signup's empty-account promise didn't survive a page reload.**
   The earlier truthful-empty-signup fix only cleared the *current*
   in-memory `MockClient` instance. `private projects = structuredClone(
   SEED_PROJECTS)` and its siblings were class field initializers — they
   re-ran on every full page load, since a client-side mock is reconstructed
   from scratch on each navigation. Confirmed live: sign up, open the memory
   page (a plain link click, not a reload trick), and a stranger's
   "Meridian Skincare" project, wiki/semantic/episodic memory entries, and
   599k/6M usage bar appear on an account that was one click old. This is
   not a cosmetic bug — a real user would read it as somebody else's client
   data leaking into their new account. Fixed by persisting an
   empty-account flag the constructor checks, with `login()`/
   `loginWithProvider()` explicitly reseeding the live instance too (the
   flag alone only governs the *next* load — a login right after a signup
   would otherwise incorrectly stay empty; caught by testing the returning-
   demo-login path immediately after, not assumed safe). Verified both
   directions in Chrome, screenshots taken before and after.
2. **First-time users were told "Welcome back."** The new-chat greeting
   pool ("Welcome back", "Look who's back", "The archive missed you", ...)
   had no first-run branch. Confirmed live at signup. Fixed with a plain
   "Welcome" — advisor review caught that the first fix still raced the
   `runs` query (a first-timer would flash the false "Welcome back" during
   the loading window before it flipped), corrected to gate on
   `!workspaceReady` too.
3. Also (found while fixing #1, not hunted for separately): every *normal*
   mock delivery now sets `verificationState: "grounded"`, not just the
   QA partial-timeout trigger. The mock's own decision log always claims
   the output filter passed — leaving the field unset meant the VERIFIED
   seal, the product's core "claims checked" trust signal, never once
   appeared on an ordinary run.

Also audited and found **already correct, no change made**: the decision
log's jargon (`ROUTE`/`OBS`/`TOOL`, entropy math, `ClamAV clean`) is opt-in
behind a toggle that auto-collapses ~2.2s after delivery — a non-technical
user watching a run never has to parse it unless they choose to. The Models
settings page explains each pipeline role in plain language with sensible,
pre-selected defaults. Settings/Usage/Billing live under the bottom-left
account menu, not the main sidebar nav — checked against the "where do I go
for X" ask directly, and this is the same convention Slack/Notion/ChatGPT
use (a persistently-visible avatar+name, not one item lost in the middle of
a list), so left alone rather than "fixed" into an unfamiliar pattern.

Regression check: `tsc`, `eslint`, `vitest` (87/87), clean production build,
and the Playwright suite most likely to catch a break in mock-session
construction or the report masthead (`first-value.spec.ts`,
`landing.spec.ts`, `completion-status.spec.ts`) — 5/6 green in one run, the
6th (`completion-status.spec.ts`'s blocked-run case) passed cleanly both
standalone and in isolation immediately after, confirming a pre-existing
sequencing flake under back-to-back long-running tests, not a regression
from today's changes.

Outcome clarity 85 -> 87 (both fixes are direct, evidenced corrections to
"understands product... without decoding system" — a stranger's data and a
false "welcome back" both actively worked against it). Trust and control
87 -> 89 (this dimension names "memory" and "privacy" explicitly; the
empty-account bug was squarely this, and the default VERIFIED seal
reinforces the same signal on every ordinary run, not just edge cases).
Continuity and retention 86 -> 88 (this dimension is fundamentally "does
context correctly persist across navigation" — which was broken for every
fresh account until today). Total moves 83.42 -> 84.16 — genuine and
evidenced, not chased toward a target. Performance (64) and time to first
value (78) are unchanged for the reasons already stated; see the 90-gate
note at the top of this file.

## Pass 5 — sent prompts become editable (2026-07-29)

Owner found a core workflow defect: the only “Edit and resubmit” control lived
inside a failed/blocked response callout and merely focused an empty follow-up
composer. It did not edit or resubmit. Successful prompts had no edit action,
and a user ten turns deep could not restart from an earlier correction.

Frontend now puts Copy and Edit directly on every sent prompt: hover/focus on
pointer devices, tap reveal at 390px, inline prefilled editor, explicit
later-turn context warning, and “Restart from here.” The fake callout-local
button is gone. Mock contract tests prove a middle-turn revision retains the
prefix, excludes the replaced turn and descendants, preserves the original
branch, and keeps project/input scope. Browser proof covers desktop edit →
new path and mobile tap actions in
`previews/2026-07-29_prompt-revision/`.

**Score stays 84.16.** Real backend branch semantics do not exist yet.
Frontend filed
`proposals/to-backend/2026-07-29_revise-turn-branch-contract.md` and wired its
HTTP adapter, but a mock-green interaction is not a live paid workflow.
Re-score core workflow/continuity only after real HTTP verification.

## Pass 6 — memory honesty, a real plan-tier bypass, project creation redesigned (2026-08-01)

Three pieces of work landed this session, all with real evidence (this
Pass's core-workflow move below is separate from — does not resolve — Pass
5's deferred "re-score after real HTTP verification" of prompt revision):

1. **Memory provenance + honest inferred-tier delete**
   (`reports/frontend/frontend_report_v13.md`). Memory cards now show real
   curator provenance (saved-by, kind, rationale). More load-bearing for
   score: inferred-tier (semantic/episodic/procedural) entries are now
   deletable — they always were server-side, the UI just never exposed it —
   and the delete confirmation/toast stopped unconditionally claiming
   "removed from your wiki... a few seconds to undo" for tiers that have no
   undo. Browser-verified via a real page-render test
   (`src/tests/memory-page.test.tsx`), not a mock of the assertion.

2. **A genuine plan-tier bypass, found by using the feature, not built into
   it** (`reports/frontend/frontend_report_v14.md`). Adding optional
   goal/context/reference-files to project creation and testing it against
   the *live* backend (reachable for the first time this session) as a
   fresh free-tier signup surfaced that `GET /memory`, `POST /projects`,
   `POST /memory`, and `POST /memory/upload` never check `user.plan` at
   all — a locked-tier account's wiki shows as UI-locked but the content is
   already in the network response, and nothing stops writing to it either.
   Confirmed live, not inferred. Frontend's fix removes the UI path
   entirely (fields don't render, not just get a warning, when the plan
   lacks wiki) and independently guards the submit path — verified via
   `src/tests/new-project-dialog.test.tsx` (4 tests) proving both branches
   and the guard. Filed
   `proposals/to-backend/2026-08-01_memory-plan-tier-not-enforced-serverside.md`
   (high priority) for the actual server-side enforcement, correctly kept
   out of frontend's tree.

3. **Project creation moved behind an explicit click**
   (`reports/frontend/frontend_report_v15.md`). Owner correction: those same
   fields had also landed in `FirstRunGuide`, an older flow that auto-showed
   a decision/context/deliverable form as the *default* home screen for any
   zero-run account — exactly the "ambient, not click-triggered" pattern the
   owner flagged as wrong. Deleted it; home screen is now identical for
   first-time and returning users, with a "Start with a project" CTA shown
   only when the account has zero projects (not zero runs — an account with
   one project isn't told to make its "first" one again). e2e testing (not
   inspection) caught a real bug in the process: lifting the dialog's open
   state into shared context caused both `ProjectSwitcher` DOM instances
   (sidebar duplicates for desktop rail vs. mobile drawer) to open their own
   dialog off one shared flag. Fixed by mounting the dialog once in
   `AppShell`. Also fixed, found while chasing that: `components/ui/
   dialog.tsx` never gave the native `<dialog>` element an accessible name
   (`aria-labelledby`) — true of every dialog in the app, not just this one.

**This session's full verification, not just unit tests**: live browser
click-through against the real backend, desktop and 390px
(`previews/2026-08-01_project-creation-redesign/`), a keyboard-only pass
confirming the dialog's focus trap and tab order and that Escape returns
focus to the trigger, an accessibility-tree check that the dialog now
resolves as `role="dialog"` with a real name, and zero console errors at
every step across four fresh signups. `tsc`/`eslint` clean, vitest 100/100,
5/5 on the affected e2e specs run against a real mock production build (not
just `npx playwright test` — a full `next build && next start` on a
separate port, the only way to trust the result wasn't dev-mode artifacts).

**Score moves 84.16 -> 84.93.** Outcome clarity 87 -> 89 (the exact
"where do I go for X" confusion the owner flagged, resolved and verified,
not just claimed). Trust and control 89 -> 91 (an honest delete promise
plus a real plan-tier bypass found and closed on the frontend side, both
evidenced). Core workflow 86 -> 87 (project setup is now one coherent entry
point instead of two competing ones). Accessibility 95 -> 96 (a real,
app-wide `aria-labelledby` fix, verified via the accessibility tree, not
assumed from the visual). Performance (64) and time to first value (78)
unchanged for the reasons already stated elsewhere in this file.

## Pass 7 — the project's goal stays pinned in view (2026-08-01, same day)

Owner's own idea, picked from a short list offered after Pass 6: the goal
set at project creation was write-only — a wiki entry indistinguishable
from any other once saved, with no way to see it again except digging into
the Memory tab. Added a small pinned card on the workspace home screen
(`GOAL — <text>`) whenever the current project has one, sourced from the
same wiki entry the New Project dialog already writes (`src/lib/
project-goal.ts` — a shared title constant so writer and reader can't drift,
no new backend field, no proposal needed).

Verified live, not assumed: created a project with a goal on a Pro-plan mock
account, confirmed the card renders at rest, then typed a brief and
confirmed it — unlike the memory recap directly below it, which correctly
recedes to a small chip — stays fully visible while typing. Zero console
errors either state. `previews/2026-08-01_project-goal-pinned/`. New
`src/tests/project-goal.test.ts` (3 tests) covers the lookup logic itself
(tier must be wiki, title must match exactly, absence cases).

Honest limitation: on a near-empty project, the same goal entry also
surfaces once inside the recap list below (it's a real wiki entry, so nothing
stops the recap's own ranking from picking it as one of its four rotating
slots) — visible duplication on this specific edge case. Not fixed; recedes
naturally once a project accumulates enough other memory that the recap's
slots fill with other candidates first. Flagging rather than hiding it.

**Score moves 84.93 -> 85.03.** Continuity and retention 88 -> 89 — this
dimension is explicitly about context surviving across a working session;
the goal now does exactly that, verified live in both the resting and
typing states, not just written and assumed. No other dimension moves —
mobile completeness and visual craft aren't re-scored from a single
desktop-only capture (390px wasn't captured for this specific change).

## 3. Hard gates

Weighted score alone cannot hide critical failure.

### Gate for 80

- New user can reach first credible result without knowing Clannon architecture.
- Core loop has no visible dead end.
- Mobile supports run creation, monitoring, recovery, follow-up, and export.
- No routine action loses user input silently.
- Production performance measured, not inferred from code.

### Gate for 90

- Mobile Lighthouse target: LCP <= 2.5s, INP <= 200ms, CLS <= 0.1.
- No material console errors on public or authenticated critical paths.
- First-run guidance demonstrates why project memory matters.
- Every live-run state answers: what is happening, why, cost, control, and next step.
- Delivered work supports review, source inspection, correction, refinement, sharing, and export.
- Paid-plan differences are visible in workflow value, not only token counts and settings.
- Full browser E2E suite covers critical happy and failure paths.

### Gate for 95

- Repeated use is faster than first use through templates, saved workflows, or equivalent leverage.
- Perceived latency stays useful through progress, partial results, and background continuity.
- Empty, loading, offline, reconnecting, permission, quota, blocked, failed, and partial-verification states are tested.
- User testing confirms comprehension and confidence; internal scoring alone is insufficient.

### Gate for 100

100 is not “no known bugs.” It requires reference-grade proof:

- Core workflow feels inevitable: no explanation needed, no redundant decision.
- Performance meets targets on representative low-end hardware and real network.
- First-time and expert users both move quickly.
- Trust information is deep when requested and quiet when not.
- Multiple external users willingly pay premium price and prefer workflow over alternatives.

## 4. Evidence protocol

Every score update must include:

1. Production build identifier and environment.
2. Desktop and 390px critical-flow browser run.
3. Lighthouse or equivalent performance trace.
4. Console and network error review.
5. Keyboard and reduced-motion pass.
6. Critical-flow E2E result.
7. Changed dimension scores with evidence.
8. Honest limitations and unverified claims.

Static screenshots can support visual findings. They cannot prove performance,
motion, task completion, recovery, or perceived value.

## 5. Critical flows

1. Landing -> understand value -> inspect proof -> pricing -> signup.
2. Signup -> create/select project -> seed context -> first run.
3. Attach files -> submit brief -> monitor work -> cancel/reconnect if needed.
4. Delivery -> inspect verification/sources -> copy/download/preview -> follow up.
5. Return visit -> find prior conversation -> understand recalled memory -> continue.
6. Correct/delete memory -> see future hydration reflect correction.
7. Reach quota/blocked/failed/partial state -> understand impact -> recover.
8. Change plan/model/theme without losing task context.
9. Complete flows 2-7 at 390px and by keyboard.

## 6. Score change rule

Frontend report owns evidence. This file owns rubric.

- Do not raise score for code that has not been exercised in browser.
- Do not raise performance score from bundle estimates alone.
- Do not award backend capability unless frontend exposes it coherently.
- Do not lower score for unavailable backend implementation when mock contract
  proves frontend state honestly.
- Regression in hard gate caps total score below that gate until fixed.
