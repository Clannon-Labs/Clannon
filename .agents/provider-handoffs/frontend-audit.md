# Shared provider handoff — frontend-audit

Independent source-read-only frontend product-security research role. Read
`frontend-audit/CLAUDE.md`, then the code-grounded threat model in
`frontend/FRONTEND_AUDIT_CHARTER.md`, after root boot files. Detailed unresolved
findings stay in gitignored reports and proposals; this tracked file carries safe
continuity only.

## Current checkpoint — F-01/F-02 retest COMPLETE (2026-08-12)

Retested exact revision `adea99a77db1cc900767d464660ab0f3b2ea30d5` from a disposable
`git archive` of the committed tree (worktree dirty: `frontend/.env.prod`). Evidence:
`reports/frontend-audit/report_v3.md`. Retest appended to the canonical frontend
proposal; comms written. **No whole-system PASS** — targeted two-finding retest.

- F-02 **RETESTED — MITIGATED** at the client boundary. Credentials (all parser forms,
  incl. `%40`/`%3A`-encoded), malformed percent escapes across path/query/fragment, and
  scheme/relative/whitespace/host/port are rejected; safe encoded + ordinary HTTP(S)
  preserved with no over-rejection. SSE parse (`run-event.ts:40`) and render sink
  (`expert-panel.tsx:83`) share one policy; rejected URLs render as a non-clickable
  `div[data-invalid-source-url]`. Bypass hunt found nothing.
- F-01 **OPEN, narrowed high -> medium.** Guard fails closed for unset, empty, mistyped
  and case-mismatched modes AND for ambient `NODE_ENV=development`/`=test` — proven with
  five real `next build` runs. One bypass survives: `next build --debug-prerender`.

**Two traps already paid for — do not re-derive:**

1. **`next build` does NOT set `NODE_ENV`.** The CLI does
   `NODE_ENV = process.env.NODE_ENV || defaultEnv` (original source readable via
   `next/dist/bin/next.map`), so an ambient value survives. From source reading alone the
   F-01 guard looks bypassable through the environment. **It is not** — Turbopack inlines
   `process.env.NODE_ENV` as a compile-time literal, `"production"` for `next build`.
   I predicted the opposite and the real build refuted me. Reading the CLI was necessary
   but not sufficient.
2. **`--debug-prerender` sets `NODE_ENV='development'` in the CLI action before
   compilation**, so the inlined literal becomes `"development"` and the guard's
   comparison can never be true. That build exits 0, is deployable (BUILD_ID, 46 static
   chunks, `next start` serves `/login` HTTP 200) and selects `MockClient`. Fastest way to
   read any build's resolved mode: grep built chunks for
   `apiMode: ("TURBOPACK compile-time value", ...)`.

**Tooling unlocked this session.** `npx` stays denied, but direct node entrypoints work:
`node node_modules/next/dist/bin/next build`, `node node_modules/typescript/bin/tsc
--noEmit`, `node node_modules/eslint/bin/eslint.js .`, `node node_modules/vitest/vitest.mjs
run`. That finally obtained the tsc/eslint coverage deferred in report_v2 (both exit 0;
Vitest 273 passed / 34 files). Turbopack **refuses a symlinked `node_modules`** pointing
outside the project root, and hardlinks fail cross-bind-mount — so `cp -a` the 759M
`node_modules` into the /tmp archive. Node 24 strips TS types natively, so a probe can
`import` the real `url-policy.ts` rather than reimplementing it.

**Sandbox note:** `frontend/.env.local` and `.env.prod` are masked as `/dev/null` char
devices (`crw-rw-rw- 1,3`), so `git diff` reports "unsupported file type". Masking, not
corruption — and it guarantees no ambient `.env` leaked into these builds.

Open: F-01 (medium, awaiting frontend's decision — accepting the flag as out of scope for
private alpha is a legitimate answer), F-05 (low residual, unchanged). F-03/F-04 remain
MITIGATED and were not re-audited; this diff does not touch their attack paths.

## Previous checkpoint — remediation retest COMPLETE (2026-08-11)

Retested exact local `main` revision
`dc2cd8e9f2c7f82bbce4d55ae8fa40c430a39c48`. Requested `e34f1f4b` resolved to
`e34f1f42e528f5662be62a1a42e96ea944ea17a5`; local main contained two later
commits, including server source-URL remediation. Full evidence:
`reports/frontend-audit/report_v2.md`. **No whole-system PASS.**

Finding states:

- F-01 **OPEN, narrowed** — unset production mode is HTTP and invalid modes fail;
  exact mock mode remains accepted by production builds and drives local mock auth.
- F-02 **OPEN, narrowed** — backend/SSE/render controls reject non-web schemes;
  frontend parser still admits credential-bearing and malformed-percent HTTP(S).
- F-03 **RETESTED — MITIGATED** — no iframe; PDF opens as a separate blob tab;
  production CSP says `frame-src 'none'`.
- F-04 **RETESTED — MITIGATED** at ASGI/frontend boundary — response body precedes
  delayed mail. Production proxy/socket equality remains deployment evidence.
- F-05 **OPEN, low residual** — production still uses `'unsafe-inline'`; actual
  build has 18 inline scripts/no nonce, but no reachable attacker-controlled inline
  sink found. Next nonce path requires dynamic rendering; do not demand header-only
  removal.

Independent checks: frontend 258 Vitest passed; TypeScript and ESLint exit 0;
backend focused 49 passed after routing audit logs to `/tmp`; three disposable
production build branches exercised; Firefox 153 actual production flows covered
unset HTTP selection, explicit mock login, PDF navigation, CSP, and two-tab storage.
Chrome/Chromium unavailable; Playwright lists 18 tests/8 files but default suite has
stale open-signup authentication and no CI workflow.

Deferred surfaces now inspected: ignored previews are not shipped; manifest has no
service worker/offline cache; drafts use identity-scoped `sessionStorage`; shared
preferences can race cross-tab but no auth/tenant boundary found; billing/error
actions admit fixed internal endpoints and revealed no XSS/open redirect path.

Routed updates appended. Backend proposal is `RETESTED — MITIGATED` and ready for
coordinator archive. Frontend proposal remains OPEN for F-01/F-02/F-05. Worktree had
unrelated concurrent changes; builds/read evidence used exact committed archive and
`git show HEAD`, never dirty source.

## Previous checkpoint — baseline audit COMPLETE, findings open (2026-08-10)

Audited rev `b517b98`, tree clean. Report: `reports/frontend-audit/report_v1.md`.
**Verdict: no PASS.** Five findings open, none retested — this role never closes its
own finding.

**Sandbox confirmed enforcing** before work started: `touch frontend/.audit-probe` ->
`Read-only file system`. Note a sharp edge: `comms/<date>/` is a read-only DIRECTORY
with your own file writable. Editors that stage a temp file next to the target fail
with EROFS; write in place instead (`cat > comms/<date>/frontend-audit.md <<'X'`).
`reports/frontend-audit/`, `notes/`, `drafts/`, and both proposal outputs behave
normally.

**Both charter seeds are resolved — do not re-litigate them as open questions.**
- Markdown link schemes: KILLED. react-markdown@10.1.0 runs `visit(tree, transform)`
  BEFORE `toJsxRuntime(..., {components})`, so a component override receives an
  already-sanitized href. 20 payloads measured -> all dangerous schemes give
  `href=""`. Probe: `drafts/probe-markdown-href.mjs`.
- Blob/PDF iframe: same-origin script execution KILLED by two independent controls
  (backend always sets a non-empty Content-Type, so no sniffing; and CSP blocks blob:
  framing). What survives is F-03 below. Probe: `drafts/probe-csp-firefox.mjs`.

**Open findings** (detail in report; proposals already routed):
- F-01 **high**, frontend — `apiMode` fails OPEN to the mock client
  (`app.config.ts:24`), whose auth is a localStorage write accepting any email + any
  8-char password as `pro`. At this revision nothing committed produces an http-mode
  build: `.env.example` says mock, `.env*` gitignored, CI sets no env, and `.env.prod`
  is NOT a filename Next loads (verified in installed `@next/env`). Silent failure.
- F-02 **medium, latent**, frontend + backend — `source.url` unvalidated end-to-end
  (`run_sources.py:19-36` -> SSE `as RunEvent` cast -> `expert-panel.tsx:83-86` href).
  NOT exploitable as written: measured that `target="_blank"` blocks `javascript:` in
  Firefox. The saving control is incidental, which is the whole point.
- F-03 **low-medium**, frontend — no `frame-src` in CSP kills the PDF preview; the
  obvious fix arms an iframe with no `sandbox`. Must be fixed together.
- F-04 **low-medium**, backend — waitlist timing oracle: mail send awaited inline on
  one branch only, defeating the deliberate identical-202 non-disclosure. Mechanism
  read; delta NOT measured.
- F-05 **low**, frontend — `script-src 'unsafe-inline'`; the amplifier for F-02. Its
  stated precondition for removal (auth cookies live) is now met.

**Verified working, so don't re-spend effort:** waitlist gate genuinely enforced
server-side (`backend/api/app.py:204-209`); no tokens in client storage; no
middleware/route handlers/`"use server"`, so no server-held secret; markdown
chokepoint sound; `text/html` artifacts render as plain text and SVG only via `<img>`.

**Deferred, carry forward.** Chrome/WebKit UNVERIFIED — `/opt` is not mounted in the
sandbox and Playwright's browsers are not downloaded, so all browser measurement is
Firefox 153 via `firefox --headless --screenshot` (read the PNG back with the image
reader; it works well). `npx tsc --noEmit` and `npx eslint .` were DENIED by the
permission layer and never ran. No live session exercised. Not yet examined: e2e
suite contents, `previews/**`, PWA/service-worker surface, cross-tab localStorage
races, billing flows beyond the error parser.

**Method note worth keeping:** Semgrep (`p/typescript`, `p/react`, `p/xss`) returned
zero findings and missed F-02, which a manual read of dynamic `href`/`src` attributes
caught. `npm audit`'s two "high" advisories are both dev-only and unreachable from the
browser. Neither tool's output was allowed to stand as a verdict in either direction.

Next session: retest anything the implementers report fixed (never self-close), then
take the deferred surfaces above.

## Earlier checkpoint — role ready; baseline audit not started (2026-08-10)

Role architecture and Bubblewrap boundary exist for Claude Code and Codex. Every
launch goes through one role-parameterized `scripts/audit-sandbox.sh`; Claude is
default, Codex explicit with `--codex`. Source, `.git`, manifests, lockfiles, project
`node_modules`, and role rules are read-only. Only notes, drafts, reports, own comms,
handoff, and routed proposal outputs are writable.

Exact isolated tooling is coordinator-owned and lock-pinned: Semgrep 1.172.0,
detect-secrets 1.5.0, npm 11.16.0, ESLint 9.39.4, eslint-config-next 16.2.12,
TypeScript 5.9.3, Vitest 4.1.9, and Playwright 1.62.0. Never install or update tools
inside the role. Codex also has Codex Security; Claude has the repo-local scanner skill
plus shared attack-path and counterevidence agents.

First work: pin revision and dirty state; refresh the frontend charter's threat model
against live code; run a standard baseline; then prioritize reachable browser/client
abuse paths. Two charter seeds require verification, not repetition as findings:
blob/PDF iframe isolation and markdown-link scheme handling. Seek counterevidence and
read backend implementation before any claim that a server-side control is absent.

No security verdict exists. No candidate risk is a finding yet.

## Earlier change note — 2026-08-10

Baseline audit executed. Both charter seeds were verified by measurement and both of
their headline claims were KILLED — the value of the pass came from what the seeds did
not name: a build-time configuration default that fails open into client-side
authentication (F-01), and a URL sink outside the charter's designated chokepoint
(F-02). Prior checkpoint retained above; its tooling inventory is still accurate,
except that Playwright's browsers are absent, so Firefox-headless screenshots are the
working measurement technique in this sandbox.

## Change note — 2026-08-11

Independent remediation retest completed after coordinator request. Previous
baseline checkpoint retained intact. Findings changed only where implementation plus
reachable behavior supported it: F-03/F-04 mitigated; F-01/F-02/F-05 remain open
with narrowed scope and explicit counterevidence.

## Change note — 2026-08-12

Targeted retest of F-01 and F-02 at `adea99a` on coordinator request; the 2026-08-11
checkpoint is retained above in full. F-02's client half moved to MITIGATED on a complete
payload matrix run against the real module. F-01 stayed OPEN but was narrowed to medium:
the environment-based bypass I hypothesised was refuted by real builds, and the surviving
bypass is a documented debug build flag rather than a misconfiguration. The load-bearing
correction recorded above is that the guard's strength comes from Turbopack compile-time
inlining, not from `next build` setting `NODE_ENV` as the source comment claims.
