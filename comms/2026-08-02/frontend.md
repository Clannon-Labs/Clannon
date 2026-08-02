# frontend — 2026-08-02

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
