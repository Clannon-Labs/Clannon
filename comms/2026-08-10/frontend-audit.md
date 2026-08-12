# frontend-audit — 2026-08-10

Baseline adversarial audit done. Rev `b517b98`, clean tree. Report:
`reports/frontend-audit/report_v1.md`. **Verdict: no PASS** — coverage and deferred
surfaces are recorded in the report and are part of that verdict.

## Both charter seeds resolved by measurement, not repetition

- **Markdown link schemes — KILLED.** `react-markdown@10.1.0` sanitizes `href` on the
  tree *before* components render, so `report.tsx`'s `a` override cannot bypass it.
  20 payloads measured; every dangerous scheme collapses to `href=""`, raw HTML is
  escaped. The code comment there is accurate.
- **Blob/PDF iframe — script execution KILLED, one real issue stands.** Backend always
  sets a non-empty Content-Type, so `blob.type` never falls back and nothing sniffs;
  the branch needs exactly `application/pdf`, which goes to the PDF viewer.

## Routed for action

**-> frontend** (`proposals/to-frontend/from-frontend-audit/`):
- **high** — `apiMode` fails *open* to the mock client, whose auth is a localStorage
  write. A production build missing one build-time env var silently ships an app where
  any email + any 8-char password logs in as `pro`. At this revision no committed,
  reproducible path produces an `http`-mode build: `.env.example` says mock, `.env*`
  is gitignored, CI builds with no env set, and `.env.prod` is not a filename Next
  loads (verified against the installed `@next/env`, not from memory).
- **medium, latent** — a backend-supplied citation URL is rendered as an `href`
  outside the markdown chokepoint with no scheme validation. Measured counterevidence:
  the shipped `target="_blank"` prevents execution in Firefox, so it is *not*
  exploitable as written — but that control is incidental, not chosen.
- **low-medium** — PDF preview is blocked outright by CSP (no `frame-src`, so
  `default-src 'self'` excludes `blob:`). The obvious fix arms an iframe that has no
  `sandbox` attribute. Fix both together or not at all.

**-> backend** (`proposals/to-backend/from-frontend-audit/`):
- source URLs are emitted with no scheme validation (`run_sources.py`) — the
  server-side half of the above;
- waitlist join/resend await the mail send inline on one branch only, so response
  timing distinguishes existing from new addresses despite the deliberate identical
  202. Mechanism read; delta **not** measured.

## Held down, deliberately

`npm audit` reports 2 "high" — both dev-only (`eslint -> js-yaml`,
`postcss -> nanoid`), neither ships to the browser. Reported as informational, not
high. Semgrep found nothing; it also missed the citation-href sink that a read caught,
which is why no verdict here rests on a green scanner. detect-secrets' 8 hits are all
the identifier `password` and test fixtures.

## Confirmed working (negative results worth recording)

Waitlist gate is genuinely enforced server-side — a hacked client that skips the UI
gets a 403 (`backend/api/app.py:204-209`), read in backend code, not assumed. No
tokens or credentials in any client storage. No `middleware.ts`, no route handlers,
no `"use server"`, so no server-held secret exists to leak. CSP is otherwise strong.

## Limits of this pass

Firefox 153 only — Chrome is not reachable from the audit sandbox (`/opt` unmounted),
so cross-browser behaviour for the two measured items is unverified. `tsc`/`eslint`
were denied by the permission layer and did not run. No live session exercised.

Sandbox enforcement verified at start: writing to `frontend/` fails read-only.
