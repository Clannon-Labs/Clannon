# Shared provider handoff — frontend-audit

Independent source-read-only frontend product-security research role. Read
`frontend-audit/CLAUDE.md`, then the code-grounded threat model in
`frontend/FRONTEND_AUDIT_CHARTER.md`, after root boot files. Detailed unresolved
findings stay in gitignored reports and proposals; this tracked file carries safe
continuity only.

## Current checkpoint — baseline audit COMPLETE, findings open (2026-08-10)

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

## Previous checkpoint — role ready; baseline audit not started (2026-08-10)

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

## Change note

Baseline audit executed. Both charter seeds were verified by measurement and both of
their headline claims were KILLED — the value of the pass came from what the seeds did
not name: a build-time configuration default that fails open into client-side
authentication (F-01), and a URL sink outside the charter's designated chokepoint
(F-02). Prior checkpoint retained above; its tooling inventory is still accurate,
except that Playwright's browsers are absent, so Firefox-headless screenshots are the
working measurement technique in this sandbox.
