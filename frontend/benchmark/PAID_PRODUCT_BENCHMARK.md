# Paid Product Benchmark

Status: ACTIVE  
Owner: frontend  
Started: 2026-07-28  
Replaces: screenshot beauty scores as primary frontend benchmark

Current verified score: **85.57 -> 86/100**  
Current evidence: `benchmark/PERFORMANCE.md`, `benchmark/FIRST_VALUE.md`,
`benchmark/REAL_JOURNEY.md`, `previews/2026-07-28_completion-status/`,
`previews/2026-08-01_project-creation-redesign/`,
`previews/2026-08-01_project-goal-pinned/`,
`previews/2026-08-01_failed-and-quota-states/`,
`previews/2026-08-02_run-notifications/`,
`previews/2026-08-02_spend-awareness/`,
`previews/2026-08-02_history-page/`, and
`reports/frontend/frontend_report_v8.md` through the latest

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
| Core workflow | 18 | 89 | 16.02 |
| Trust and control | 12 | 93 | 11.16 |
| Continuity and retention | 10 | 90 | 9.00 |
| Performance and smoothness | 12 | 64 | 7.68 |
| Failure recovery | 7 | 90 | 6.30 |
| Accessibility | 5 | 96 | 4.80 |
| Mobile completeness | 5 | 88 | 4.40 |
| Visual and interaction craft | 4 | 95 | 3.80 |
| **Total** | **100** |  | **85.87 -> 86** |

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

## Pass 8 — failed and quota-exceeded, the last two dark states (2026-08-01, same day)

Gate-95 names four states that must be tested: "blocked, failed, and
partial-verification states." Blocked and one partial-verification cause
(timeout) closed weeks ago; failed and the rate-limit/quota partial cause
never had a QA path to reach them at all — same shape of gap as blocked was
before it got one.

Added two mock QA triggers (`src/lib/api/mock.ts`, same keyed-off-brief-text,
never-surfaced-as-a-suggestion pattern as the existing ones): "force a failed
run for e2e" reaches a genuine `status: "failed"` terminal for the first
time; "force a quota exceeded for e2e" reaches `completionState: "partial",
completionReason: "rate_limit"` — quota exhaustion's closest existing model
in this app, since there's no separate RunStatus for it. Both already had
written UI copy (the generic failed-run alert, `CompletionBanner`'s
rate-limit case) that had simply never been exercised in a browser.

Went further than the trigger, into the actual pre-run quota-exhaustion
moment (not just mid-run interruption), because testing it surfaced two real
gaps, not built into the ask but too directly relevant to leave once found:

1. **The composer didn't know the account was out of tokens.** The
   sidebar's exhausted card already existed (UI_SPEC §1, §13) with a calm
   "upgrade to continue" state — but `Composer` (the thing you actually use
   to try to send) had zero awareness of it. Send stayed live even with the
   sidebar showing zero budget left, and the sidebar isn't always in view
   (collapsed rail, mobile). Added `useBudgetExhausted()`
   (`src/lib/api/hooks.ts`, one shared computation — sidebar's own inline
   version now calls it too, replacing a second copy of the same check) and
   a `budgetExhausted` prop on `Composer`, wired at both call sites (the
   workspace home screen and the run-reply composer): Send disables, Enter
   no longer submits, and a calm inline message explains why with an
   upgrade link — typing itself is never blocked, only sending.
2. **A real backend error would have rendered as generic noise.** Read
   `backend/api/billing.py`'s `admit_run` (confirming the real backend
   already enforces this server-side, correctly — no proposal needed there)
   and found its 402 response nests the actual reason one level down
   (`{"detail": {"code": ..., "message": "Token budget exhausted...", ...}}`)
   — a shape `http.ts`'s `errorMessage()` didn't handle, silently falling
   back to a generic status-text message instead. Fixed the parser to
   unwrap the structured-detail case (and added `errorCode()`, previously
   half-implemented and reading from the wrong place entirely). Also added
   the equivalent admission check to the mock (`usedAndBudget()`, shared
   with `getUsage()`) so mock testing has the same real refusal a bypassed
   or race-condition submission would hit against the live backend, instead
   of silently accepting unlimited runs regardless of budget.

**A process mistake, self-caught**: while writing a mutation check for the
Enter-key gating test (confirming it would actually fail if the fix were
reverted — not decorative), used `git checkout --` on the composer file to
undo a deliberate one-line mutation and it discarded the ENTIRE uncommitted
feature instead, not just that line. Caught immediately by grepping for
`budgetExhausted` in the file and finding nothing. Reconstructed the exact
same diff from the conversation's own record of the edits and re-verified
everything (typecheck, lint, full suite, the mutation check itself) before
moving on. `git checkout --` is now off the table for anything but a file
with zero uncommitted work worth losing — a stash or a targeted revert of
the specific hunk is the safe move otherwise.

**Verification**: `tsc`/`eslint` clean, vitest 109/109 — new
`src/tests/composer.test.tsx` (4 tests, including a same-file sanity check
proving the Enter-to-submit path is actually reachable in this test harness
before trusting a test that asserts it's blocked — `isFinePointer()` reads
`matchMedia`, which the global test setup always stubs `false`, so a naive
version of this test would have silently proven nothing) and
`src/tests/http-error-parsing.test.ts` (2 tests, pins both the structured-
detail bug and the still-working plain-string case). Full mock-mode e2e run
(production build, port 3100, exact PID recorded and killed precisely this
time — see the process-mistake note above) — 5/5 on
`completion-status.spec.ts` including both new tests, 2/2 on
`first-value.spec.ts` unaffected. `previews/2026-08-01_failed-and-quota-states/`.

**Score moves 85.03 -> 85.29.** Failure recovery 88 -> 90 — two previously
dark states (gate-95's own list) now genuinely tested, plus the composer
now prevents a failure proactively instead of only explaining one after the
fact. Trust and control 91 -> 92 — the composer finally honors the spend
limit it displays; that contradiction (sidebar says stop, composer says go)
was a real trust gap, now closed and verified end to end, not just typed.

## Pass 9 — run-completion notifications, and a real feature deliberately not built (2026-08-02)

Owner asked frontend to find a genuine premium-vs-normal differentiator that
had never come up, and build it. Surveyed the app against this file's own
Gate 90 checklist ("sharing" and "delivered work supports review... next
step") via an `Explore` agent's 10-question audit, not from memory —
confirmed command palette and theming are already premium-grade
(`command-palette.tsx`, `theme.tsx`), and that nothing anywhere sets
`document.title`, uses the `Notification` API, or offers a share link.

**Sharing was the first instinct and the wrong one this session.** An
advisor review caught that the strongest-looking citation for "share is
missing" — `REAL_JOURNEY.md`'s "no claim-level correction/share/version
workflow" — actually scopes all three words to *claims inside a report*, not
a whole-run public link; it isn't independent confirmation of the same gap.
More importantly: a one-click public link is real new attack surface on a
private alpha whose seed data is a named client's confidential business
context, and building it in the same session it was conceived, unreviewed,
would have been the wrong call regardless of the citation. **Filed instead of
built**: `specification/api/requests/2026-08-02_run-share-link-create-
revoke.md` and `..._public-share-page-fetch.md` — the create/revoke contract
and the public read-only fetch, with the non-disclosure and token-
unguessability requirements spelled out as non-negotiable, for backend to
prioritize or push back on. No frontend UI or route exists for this yet.

**What shipped instead**: runs take minutes (sequential orchestrator rounds
— the same latency this session's earlier proposal to backend named as the
real cost), and nothing told you when one finished if you weren't watching
the tab. Added `src/lib/use-run-completion-notice.ts`, wired into `RunPage`:
a tab-title flash (no permission needed, always on) plus an opt-in real OS
`Notification` (Settings → Account → Notifications, a new `Switch` primitive
— `src/components/ui/switch.tsx`, nothing binary-and-inline existed in the
design system before). Both trigger only on a genuine live→terminal
transition while `document.hidden`, skip `cancelled` (user-initiated, not
worth interrupting for), and restore the title on `visibilitychange` or
unmount. Explicitly scoped to "this run's page is open in a background tab"
— the SSE stream only runs while `RunPage` is mounted, so navigating
elsewhere *within* Clannon stops tracking a run same as it already stops
rendering it live; app-wide tracking regardless of open page would need a
second, parallel subscription mechanism and was deliberately left as a
separate, real follow-on rather than folded in here (LAW 1).

**Verification, in order of strength**: `tsc`/`eslint` clean, vitest
149/149 (15 new tests — `notify-preference.test.tsx`,
`use-run-completion-notice.test.tsx` — covering permission-gated persistence
and every transition edge case). Then, because this benchmark's own protocol
says static screenshots can't prove task completion: a **live, real-browser,
end-to-end run** against the mock backend — submitted a real brief, forced
`document.hidden = true` via Playwright, waited out the full ~38s mock run
script, and read the actual page title afterward: `"✓ Report ready ·
Clannon"`. Flipped visibility back and dispatched `visibilitychange`: title
read back exactly `"Workspace · Clannon"`. Zero console errors across the
sequence. Separately verified both real permission paths live (Chromium's
actual default-denied response correctly left the toggle off and
unpersisted; a stubbed granted permission correctly persisted it and turned
the switch on). `previews/2026-08-02_run-notifications/`.

**Score moves 85.29 -> 85.47.** Core workflow 87 -> 88 — this dimension
names "review" as part of the coherent brief→run→review→reuse loop, and not
knowing when the run half of that loop finished was a real gap in it,
closed and proven live. **Not** claiming Trust and control or Continuity —
Gate 90's "every live-run state answers... next step" is a hard-gate
phrase, not one of the ten scored dimensions, and this closes it partially
(one run, one tab) rather than fully; inflating a scored dimension to match
gate language would be exactly the vacuous-pass shape this file's own
scoring rules warn against. Accessibility not re-scored: the new `Switch` is
a real `role="switch"` with `aria-checked` and a labelled accessible name,
but wasn't separately screen-reader-tested this pass.

## Pass 10 — spend awareness: a duration estimate and a budget forecast, no score change claimed (2026-08-02)

Second research pass this session, after run-completion notifications (Pass 9).
Owner asked for more premium-vs-normal gaps; a fresh `Explore` audit (10 new
questions, disjoint from the first pass) turned up ten candidates. The most
consequential finding wasn't a UX gap at all: `backend/api/app.py:193-198` +
`auth.py:177-190` show `POST /auth/signup` has zero invite/allowlist gating,
contradicting root `CLAUDE.md`'s stated private-alpha model. Filed as
`specification/api/requests/2026-08-02_signup-not-invite-gated.md`, HIGH
priority, for the owner/backend to pick a contract (invite code / email
allowlist / approval-gated login) — not frontend's call to make, and not
something a client-side field could enforce anyway (the exact lesson the
plan-tier bypass already taught).

Also found, verifying before building: `GET /runs/archive` is listed in
`ROUTES.md` but doesn't exist anywhere in `backend/api/*.py` — a real
discrepancy in the route table, not a frontend gap. Filed as
`2026-08-02_runs-archive-route-not-implemented.md` instead of building a
history page against a route that would always be empty.

**What shipped**: `GET /usage`'s real backend response has always included a
`latency` block (p50/p95 duration samples — `backend/api/billing.py:263-277`)
that the frontend never once read (`grep` across `types.ts`/`http.ts`/
`mock.ts` — zero hits). Added the type, wired the mock to record real
elapsed time per completed run (`mock.ts`'s `streamRun`, mirroring the
backend's own percentile math), and built two small features from data
that was already being fetched: a composer caption ("Runs like this usually
take about 4 minutes") sourced from the account's own p50, and a budget
forecast ("~N days left at this pace") in `usage-summary.tsx`, derived from
the already-rendered daily-spend chart. Both degrade to nothing — never a
fabricated `0` or an instant guess — when there isn't enough real history
yet (`usage-forecast.ts`, `formatDurationEstimate`/`estimateDaysRemaining`).

**No score change claimed, deliberately.** Both features are returning-user
capabilities — they need the account's own run history to say anything at
all, and stay silent otherwise. That means neither actually touches "Time to
first value" (this dimension measures the first-ever signup-to-deliverable
journey, and a brand-new account has no history to source an estimate from —
checked this before scoring, not after). "Continuity and retention" is the
closer fit conceptually, but the mock's seed data backing this pass's live
verification was two data points, not a real usage history — thin grounds
for a dimension move. Recording the capability honestly; a future pass with
real accumulated usage (or real backend verification) is the right place to
revisit whether this earns a score change.

Verified: `tsc`/`eslint` clean, vitest 169/169 (18 new tests — pure
duration/forecast-formatting logic, composer wiring across five states,
usage-summary rendering, and a mock integration test proving `getUsage()`
assembles real elapsed-time samples as runs actually complete, not just
synthetic seed data). Live browser: logged into the mock demo account,
confirmed the composer caption and the usage forecast both render with real
seeded numbers (599k/6M used, two real daily-spend days → "about 18 days
left"), zero console errors. `previews/2026-08-02_spend-awareness/`.

## Pass 11 — a real History page, no new API, crosses 85 (2026-08-02, same day)

Third build this session, closing the gap flagged at the end of v18's
report and Pass 10: the sidebar's "Recent" list has no search, no status
filter, and no dedicated view — just a flat, unlimited scroll in a narrow
rail. `GET /runs` already returns full unfiltered summaries (confirmed by
reading `client.ts`'s `listRuns` signature and both backends), and
`groupBySession` (`lib/sessions.ts`, already shared by the sidebar) already
gives title/status/createdAt/turnCount/tokensUsed per conversation — this
needed zero new API, only a page that does something with data already
being fetched.

Added `src/app/app/history/page.tsx`: a real "Every run" view with a search
box (title substring, client-side) and status-filter pills (All/Delivered/
Blocked/Failed/Cancelled), scoped to whatever project the sidebar switcher
currently has selected (including "All projects," which already existed as
an option). Wired into `APP_NAV` (`nav.config.ts`) so it appears in the
sidebar's Sections row next to Memory, and into the ⌘K command palette as a
"Go to" jump. Distinguishes a genuinely-empty account ("Nothing here yet")
from a filtered-to-nothing state ("No matches") — the two are different
findings and read differently to a user.

Explicitly did **not** wait on the two open backend requests from Pass 10
(`2026-08-02_runs-archive-route-not-implemented.md`,
`2026-08-02_signup-not-invite-gated.md`) — the archive-route question
only affects whether a *separate*, superseded/revised-runs view could
exist someday; the actual "search my past work" gap this closes needed
none of that.

**Score moves 85.47 -> 85.57 (85 -> 86).** Continuity and retention 89 -> 90
— this dimension's own stated definition is *"Returning work becomes
easier; projects, sessions, memory, **search**, and follow-ups preserve
context"* (§2 table, word for word); a searchable/filterable history view is
about as direct a match to a dimension's own listed criteria as this
benchmark gets. **Not** separately moving Core workflow, even though
"reuse" is one of its named criteria too — one precise match is honest
evidence; claiming the same shipped feature against two dimensions at once
is the kind of double-dipping this file's scoring rules exist to prevent.

Verified: `tsc`/`eslint` clean, vitest 175/175 (6 new tests —
`history-page.test.tsx`: newest-first ordering, search filtering, status
filtering, combined filters producing a genuine no-matches state, and the
empty-account/loading states kept distinct). Live browser: real seeded
demo account, search and status-filter pills both exercised live, zero
console errors, desktop and 390px.
`previews/2026-08-02_history-page/`.

## Pass 12 — print/PDF export for delivered reports, bulk delete on History (2026-08-02, same day)

Fourth build this session, from a third Explore survey plus two already-flagged
backlog items, narrowed with an advisor review to the two with real premium
value and zero new backend surface. Full reasoning: `reports/frontend/frontend_report_v21.md`.

**Print/PDF export.** No `@media print` rules existed anywhere in the app —
printing a delivered report today would print the full sidebar, composer, and
activity log around it. Added a `#printable-report` target on the report card
and a Print button next to the existing Copy/Download row. Deliberately used
the browser's native print engine (`window.print()`), not a client-side PDF
library — the standard path for HTML/CSS content, and how Notion/Linear/GitHub
all do it.

Two real, non-obvious bugs surfaced only by generating an actual multi-page PDF
(not a single-page screenshot, which looked fine and hid both):
`position: absolute; inset: 0` on the printable container breaks across a page
boundary (Chromium's containing block for paginated print is the single page
box, not the whole document — the white background stopped at page 1 and page
2 fell back to the app's dark theme), and the report's markdown table used
theme tokens (`bg-muted`, `border-border`) that stayed at their live dark-mode
values regardless of print, so a printed table header rendered dark-on-dark.
Both fixed; verified against a real generated PDF, not a screenshot proxy.
Detail in `previews/2026-08-02_print-export-and-bulk-delete/`.

**Bulk delete on History.** Natural extension of the History page (Pass 11) —
`DELETE /sessions/{id}` already existed and was already used by the sidebar's
per-row delete. Added checkboxes, a selection toolbar, and a confirm dialog
that names the count (never a generic "delete selected?"). Deletes run
sequentially against the one shared mutation and tally the result honestly —
"3 of 4 deleted" on a partial failure, never a false clean-success toast.

**Also fixed while testing, unrelated to either feature above**: a genuine,
previously-undetected bug in `use-templates.ts` (shipped in Pass "wire
templates," earlier this session) — the no-user branch of `getSnapshot()`
returned a fresh `[]` literal every call, the same `useSyncExternalStore`
defect already fixed for the keyed case but missed for the null-key one. Only
manifests on a cold `/app` load where `userId` is briefly `undefined` before
auth resolves, which is why three earlier rounds of live testing never hit
it. One-line fix, reproduced red-then-green with a new regression test
(`src/tests/use-templates.test.ts`) before trusting it fixed.

**Score moves 85.57 -> 85.75 (86 stays 86).** Core workflow 88 -> 89 — this
dimension's own stated definition names *"review, refinement, **export**, and
reuse"* as part of the one coherent loop (§2 table, word for word); print/PDF
is the first complete export path the product has (Copy/Download hand back
raw markdown, not a presentation-ready document). **Not** claiming a second
dimension for bulk delete — it's real housekeeping value but doesn't match any
dimension's own listed criteria as directly as the History page itself already
did in Pass 11, and claiming it again would be the double-dipping this file's
rules exist to prevent.

Verified: `tsc`/`eslint` clean, vitest 182/182 (8 new tests: 3 in
`use-templates.test.ts` — the regression test above — and 5 extending
`history-page.test.tsx` for selection, clean bulk delete, partial-failure
tally, and redirect-if-viewing-a-deleted-run). Live browser: print output
verified via a real generated PDF after finding and fixing both bugs above;
bulk delete exercised end-to-end against the mock backend on desktop and
390px, zero console errors throughout — including confirming the `/app`
cold-load crash is gone after the templates fix.
`previews/2026-08-02_print-export-and-bulk-delete/`.

Also filed, not built (real gap, needs actual Stripe-shaped backend design
before any frontend UI would mean anything):
`specification/api/requests/2026-08-02_billing-cancel-downgrade-invoices.md` —
no cancel-subscription, downgrade, or real invoice/receipt history exists
anywhere (`billing-settings.tsx` explicitly disables downgrade through mock
checkout, and `useBillingPortal` returns a checkout-event log, not invoices).

## Pass 13 — real PWA icon set + iOS home-screen metadata, no score claimed (2026-08-02, same day)

Fifth build this session. The manifest shipped one 305×305 icon, no 192/512
pair, no `purpose: "maskable"`, no apple-touch-icon — flagged in the same
Pass-12 survey and deferred at the time as a design-asset problem (upscaling a
305px source badly). That call was wrong: read the actual source
(`public/brand/clannon-logo-symbol.png`) instead of assuming — it's a flat,
high-contrast geometric mark with no fine detail, exactly what a 1.68×
Lanczos upscale handles cleanly. Verified visually (all four generated files)
before shipping, not assumed.

Generated `icon-192.png`/`icon-512.png` (transparent, "any"),
`icon-maskable-512.png` (solid brand-color background, mark padded to the
safe zone so a circular OS mask doesn't clip it), and `apple-touch-icon.png`
(180×180, solid background). Wired into `manifest.ts`'s icons array and
`layout.tsx`'s `metadata.icons`/`appleWebApp`, neither of which existed
before.

**Not claiming a score move.** The honest home for this would be Mobile
completeness ("core paid workflow remains usable and legible on phone, not
merely responsive"), but a correct home-screen icon is thin evidence for
that, and the stronger claim — "the app is now installable" — was
deliberately NOT verified: recent Chrome can still gate the automatic install
prompt behind a registered service worker, which this app doesn't have (a
real, separate decision — a naive offline cache on a live-SSE-streaming app
would show stale run state as current, worse than no offline support at
all). What's actually verified is narrower: iOS Safari's Add-to-Home-Screen
doesn't need a service worker and now reads the right metadata. Filing the
score-worthy claim honestly means filing no claim this pass.

Verified: `tsc`/`eslint` clean, vitest 185/185 (3 new —
`src/tests/manifest.test.ts`, mutation-checked: reverted `manifest.ts` alone,
watched 2 of 3 tests fail with the exact defect this fixes, restored, watched
all 3 pass). Direct `curl` against a production build on :3100: manifest JSON
valid with all three icon entries, all four icon URLs `200 image/png`, and
the real HTML head carries the `icon`/`apple-touch-icon` `<link>` tags. No
page-content screenshots — this doesn't render inside a page, it renders in
browser chrome / OS home screen; recorded why in
`previews/2026-08-02_pwa-icons/README.md` per this file's own escape hatch
for genuinely nonvisual work.

## Pass 14 — real cancel/downgrade/invoices, built ahead of the backend (2026-08-03)

Owner set a standing policy this session: build the UI fully against mock, file the
exact contract to backend, ship now — filing the contract IS the unblock, not a
reason to wait. `specification/api/requests/2026-08-02_billing-cancel-downgrade-
invoices.md` was filed propose-only two passes ago (billing depth was real but
"backend-shaped"); this pass builds the real thing against that same contract.

`ClannonClient` gained `getInvoices`/`cancelSubscription`/`undoCancelSubscription`/
`downgradePlan`, implemented honestly in `MockClient` (real working simulation,
persisted via localStorage the same way `EMPTY_ACCOUNT_KEY` already was, so it
survives a reload) and as thin passthroughs in `HttpClient` (will 404 until backend
builds the routes — same as any other pending-contract call, and three tests pin the
exact request shape so drift gets caught when it lands).

Resolved a real design question the filed contract had explicitly left open (whether
"scheduled" cancellation/downgrade makes sense for this product's fixed-budget
billing model): cancel is always scheduled for the current period's end, never
immediate; downgrade is always immediate and only offered between paid tiers — Free
isn't a downgrade target, since Cancel already gets you there on its own schedule,
and two paths to the same state with different timing was the wrong design. Updated
the spec file with the resolution rather than leaving it as an open question backend
would have to guess at.

**A real bug, caught live, not by the type system**: the downgrade confirm dialog
read "Your budget changes to 2Mtokens immediately" — missing space. Source had a
literal space on the same line as the interpolated value; JSX's whitespace-collapsing
rule ate it because the surrounding paragraph wrapped across a line break further
down. Confirmed via the accessibility tree (not just the screenshot) that the DOM
text really was missing the space, not a rendering artifact. Fixed with an explicit
`{" "}`.

Verified end-to-end live, not just per-mutation: downgrade Pro→Starter (plan card,
sidebar budget, usage widget, and the Cancel section's own copy all reactively
updated together) → cancel subscription (scheduled banner names the real period-end
date) → undo via "Keep my plan" (banner clears, Cancel section reappears) → a fresh
signup confirms genuinely empty invoices and no inherited stale cancellation flag
from browser storage (the same bug class as `EMPTY_ACCOUNT_KEY` once was, checked
deliberately this time). Zero console errors throughout.

`tsc`/`eslint` clean, vitest 198/198 (13 new: 10 in `billing-cancel-downgrade-
invoices-mock.test.ts`, 3 extending `billing-client.test.ts`).
`previews/2026-08-02_billing-cancel-downgrade-invoices/`.

**Score moves 85.75 -> 85.87 (86 stays 86).** Trust and control 92 -> 93 — this
dimension's own definition names *"cancellation"* explicitly among what must be
"understandable and controllable" (§2 table, word for word), and there was
previously zero cancellation path in the product beyond a static link to the refund
policy. Not claiming a second dimension — downgrade/invoices are real value but
don't match any other dimension's own listed criteria this precisely.

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
- Paid-plan differences are visible in workflow value, not only token counts and
  settings. **Verified PASS, 2026-08-02** — not just on the Billing tab: locked
  wiki-tier fields disappear from project creation with a "not offered on your
  plan" nudge (`new-project-dialog.tsx:39,137-139`), the Memory page shows a
  locked-tier empty state per tier with a plans link (`memory/page.tsx:349,371-378`),
  and locked model roles read "System managed" inline in the composer's own model
  picker (`model-picker.tsx:194-198`). Recording this so a future session doesn't
  re-flag it as an open gap.
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
