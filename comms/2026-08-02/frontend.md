# frontend — 2026-08-02

## Run history/search shipped, no new API — benchmark crosses 86

Third build this session. `/app/history`: search by title + status-filter
pills (All/Delivered/Blocked/Failed/Cancelled), scoped to the current
project-switcher selection. Zero new backend surface — `GET /runs` already
returns everything unfiltered and `lib/sessions.ts`'s `groupBySession`
(already shared with the sidebar's own "Recent" list) already had every
field a filterable view needs. Wired into `APP_NAV` and the ⌘K palette as
a "Go to" jump. Didn't wait on either of the two backend requests filed
below — the archive-route question only gates a separate superseded-runs
view, not this.

`tsc`/`eslint` clean, vitest 175/175 (6 new tests). Live-verified: search
and status filtering both exercised in a real browser, zero console
errors, desktop + 390px. `previews/2026-08-02_history-page/`.

**Benchmark: Continuity and retention 89 -> 90** — its own definition is
"returning work becomes easier... search... preserve context," word for
word what this ships. **85.47 -> 85.57, crossing 85 -> 86.** Deliberately
declined a second dimension move (Core workflow's "reuse" criterion also
applies, but claiming one feature against two dimensions is the
double-dipping the scoring rules exist to prevent). Full detail:
`benchmark/PAID_PRODUCT_BENCHMARK.md` Pass 11,
`reports/frontend/frontend_report_v20.md`.

## HIGH: signup has zero invite/allowlist gating — contradicts the stated private-alpha model

Backend/owner: please read `specification/api/requests/2026-08-02_signup-not-
invite-gated.md` first, before anything else in this file. Verified by
reading `backend/api/app.py:193-198` + `auth.py:177-190` directly — `POST
/auth/signup` has no invite code, allowlist, or approval gate, only a
password check and a rate limit. Root `CLAUDE.md` says this is meant to be
a private alpha the owner personally admits testers into. Not frontend's
call to fix (a client-side gate on an ungated endpoint is theater — the
plan-tier bypass already proved that pattern doesn't hold). Named three
possible contracts in the request and left the choice open. This should
land before the domain goes live, not be discovered after.

Also filed, lower priority: `2026-08-02_runs-archive-route-not-implemented.md`
— `GET /runs/archive` is in `ROUTES.md` but doesn't exist anywhere in
`backend/api/*.py` (grepped directly). Discrepancy report, not a feature ask.

## Spend awareness shipped: a duration estimate and a budget forecast, no score inflated

Second build this session. `GET /usage`'s real response has always carried a
p50/p95 run-duration `latency` block (`backend/api/billing.py:263-277`) —
the frontend never once read it (grepped `types.ts`/`http.ts`/`mock.ts`,
zero hits). Wired it in: a composer caption ("Runs like this usually take
about 4 minutes") and a budget-page forecast ("~N days left at this pace"),
both sourced from data already being fetched, both degrading to nothing
(never a fabricated number) without enough real history.

**Declined to claim a benchmark score move** — checked before scoring, not
after: both features need the account's own run history, so neither
actually touches "time to first value" (that's the first-ever signup
journey; a brand-new account has zero history to source an estimate from).
Recorded the reasoning in `benchmark/PAID_PRODUCT_BENCHMARK.md` Pass 10
rather than inflate it. Also fixed a stale gate item while in there: Gate
90's "paid-plan differences visible in workflow" was actually already true
(this session's survey found three concrete citations) and had no verdict
recorded — annotated PASS so it stops looking like an open gap.

`tsc`/`eslint` clean, vitest 169/169 (18 new tests, including a mock
integration test proving `getUsage()` reflects a really-completed run's
elapsed time, not just synthetic seed data). Live browser verified with
real seeded numbers, zero console errors.
`previews/2026-08-02_spend-awareness/`. Full detail:
`reports/frontend/frontend_report_v19.md`.

Deferred, surveyed but not built (real gaps, all need actual backend
design before frontend UI would mean anything): session/device management,
account data export/deletion, an attachment library, bulk run actions.

## Run-completion notifications shipped; a share-link feature filed to backend instead of built

Owner asked frontend to find a genuine premium-vs-normal UX differentiator
nobody had discussed and build it. Surveyed the app against
`benchmark/PAID_PRODUCT_BENCHMARK.md`'s own Gate 90 checklist via an
`Explore` agent (10 concrete code-grounded questions, not memory) — command
palette and theming turned out already premium-grade.

Sharing looked like the answer first, and an **advisor review caught a real
misread**: my strongest citation (`REAL_JOURNEY.md`'s "no claim-level
correction/share/version workflow") scopes to per-claim affordances inside a
report, not a whole-run public link — not independent confirmation of what
I thought it confirmed. More importantly, a one-click public share link is
real new attack surface on a private alpha whose seed data is a named
client's confidential business context — exactly the kind of thing the
owner's stated bar ("a tester should not find any vulnerabilities") is
about. **Filed the contract instead of building it this session**:
`specification/api/requests/2026-08-02_run-share-link-create-revoke.md` and
`..._public-share-page-fetch.md`, non-disclosure and token-unguessability
spelled out as requirements. No frontend UI/route for this exists yet —
genuinely not coping with a stub, just not started.

**What shipped**: nothing tells you when a run finishes if you're not
watching the tab, and runs take minutes (the same sequential-orchestrator
latency this session's earlier proposal named). Added tab-title flash (no
permission needed) + an opt-in real OS `Notification` (new Settings →
Account → Notifications toggle, a new `Switch` primitive — nothing
binary-and-inline existed in the design system before). Fires only on a
genuine live→terminal transition while the tab is backgrounded; skips
`cancelled`; scoped honestly to "this run's page open in a background tab,"
not app-wide (documented why in the benchmark entry, not hidden). Zero new
backend API needed.

Verified: `tsc`/`eslint` clean, vitest 149/149 (15 new tests). Then a live,
real-browser, end-to-end run against mock — forced `document.hidden`,
waited out the real ~38s run script, Playwright's own page-title readout
after: `"✓ Report ready · Clannon"`, then confirmed restore-on-visibility.
Zero console errors. Both real Chromium permission paths (denied/granted)
verified live too. `previews/2026-08-02_run-notifications/`.

**Benchmark**: Pass 9, core workflow 87→88, **85.29 → 85.47** (rounds to
85). Full writeup incl. why trust/control and continuity are NOT claimed:
`benchmark/PAID_PRODUCT_BENCHMARK.md`. Report: `reports/frontend/
frontend_report_v18.md`.

## Templates wired into composer + home screen; real useSyncExternalStore bug caught live (commit e9c4e4a, pushed)

Finished what yesterday's session deliberately left uncommitted: the
templates foundation (`src/lib/templates.ts`, `use-templates.ts`,
`template-card.tsx`) is now live. `Composer` gained a "Save as template"
trigger (Star icon, next to Attach — disabled below the brief min-length)
that hands back the current session models, plus a `loadTemplate` prop that
restores a template's model overrides through a new `session.replace()` in
`useSessionModels`. `page.tsx` renders saved `TemplateCard`s ahead of the
starter examples; Use loads brief+models+project (best-effort — a since-
deleted project just falls back via the existing `useCurrentProjectId`
staleness handling), Save shows a toast, Delete removes.

Playwright click-through against the mock backend (extension wasn't
connected this session, fell back to the Playwright MCP server) caught a
real bug the foundation's own unit tests couldn't: `useTemplates`'s
`getSnapshot()` reparsed JSON on every call, returning a new array reference
each time — invalid for `useSyncExternalStore`, and never exercised in an
actual mounted tree until today. It looped forever the instant `page.tsx`
rendered it, tripping the error boundary on `/app`. Fixed with a per-user
snapshot cache in `use-templates.ts`, invalidated on save/remove. Re-verified
live: save → toast → card renders → reload persists it → Use restores the
brief → Delete removes cleanly, zero console errors after the fix. Added 5
tests to `composer.test.tsx` covering the trigger's enabled/disabled state,
the `onSaveTemplate` payload, and `loadTemplate` apply/re-apply. `tsc`/
`eslint` clean, vitest 134/134. Previews:
`frontend/previews/2026-08-02_wire-templates/`.

Checked `proposals/to-frontend/` first: one FYI-only item from backend
(`specification/api/` is now the route-shape authority, no reply needed).
`frontend/proposals/` empty.

## Extreme-priority billing proposal executed; real worker/interactive collision found and resolved (commit e53197f, pushed)

Backend's `2026-08-01_fixed-billing-and-mock-checkout-contract.md` (extreme
priority) landed in my inbox mid-session. Also wrote and filed
`proposals/to-backend/2026-08-01_time-to-first-value-latency-ideas.md`
(normal priority) — grounded in actually reading
`core/orchestrator/loop.py`, `experts/`, `models.yaml` first: sequential
orchestrator rounds (not expert parallelism, which is already concurrent)
are the real latency multiplier, report streaming is faked (single pass
chunked after the fact, not genuinely progressive), and no p50/p95
telemetry exists anywhere I could find. Three concrete, falsifiable
questions for backend, not a vague "make it faster."

**Real coordination collision, caught mid-flight**: while implementing the
billing proposal myself, files I hadn't touched kept showing up modified —
turned out the backend coordinator had dispatched a headless
`frontend-worker` onto the *exact same proposal*, into the *exact same
working directory*, running concurrently with me — despite the proposal's
own text saying it wouldn't do that because my tree was already dirty.
Stopped editing those files immediately rather than race it (two writers on
`types.ts`/`http.ts`/`mock.ts`/`composer.tsx` at once is exactly how work
gets corrupted). Waited ~40 minutes for the worker to exit, then
independently reviewed and verified its output before committing it as
frontend's own work: `tsc`, `eslint`, vitest 129/129 — matched the worker's
own claimed numbers exactly, spot-checked several files for quality (all
good — it extended, not clobbered, this session's earlier
`budgetExhausted` composer work). Backend-coordinator had *also*
independently reviewed and archived the proposal by the time I got there —
both sides converged on the same verified result without either seeing the
other's review. Commit `e53197f`, pushed.

Used the dead-time waiting productively: prepped the templates/saved-
workflows feature (owner-requested, scoped via 3 quick questions —
full-setup templates: brief+models+project, shown alongside starter cards,
account-wide for v1) in files the billing work never touched
(`src/lib/templates.ts`, `use-templates.ts`, `template-card.tsx`, 7 tests,
all green) — foundation is done and tested, UI wiring into
`page.tsx`/`composer.tsx` is the next session's first task, deliberately
left uncommitted since that wiring needs the now-settled billing composer
changes as its base.

Session score work (Pass 6/7/8, 84.16 → 85.29) and the failed/quota-state
closure are in yesterday's `comms/2026-08-01/frontend.md` and
`reports/frontend/frontend_report_v13.md` through `v17.md`. Also added two
standing `frontend/CLAUDE.md` instructions today per owner ask: don't stop
at a small benchmark bump, keep proposing UX work unprompted; and treat the
backend agent as a collaborator to propose real ideas to, not just a
dependency to escalate to when blocked.
