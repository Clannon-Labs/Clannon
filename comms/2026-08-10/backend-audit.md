# backend-audit — 2026-08-10

Bounded defensive synthesis complete at `b517b98`. Report:
`reports/backend-audit/report_v1.md`. Verdict: **PARTIAL / private-alpha STOP**;
large threat-model surfaces remain deferred, so no whole-system PASS.

Validated launch blockers:

- High: owner-canonical `CLANNON_ENV` does not activate startup strict config or YARA;
  legacy-only production mode selects dev mail. Secret-free matrix measured both.
- Medium but alpha STOP: production mail config is resolved only on first send, not
  before serving; failure is hidden behind generic waitlist 202.
- High: owner-disabled `http.request` and `delivery.notifier` remain registered,
  full-grant, and model-reachable. No network request was made.

Waitlist mail latency remains Medium timing concern; real-provider delta unmeasured.
Frontend citation-scheme premise was not validated: current sole source producer
extracts only HTTP(S), though sink-side validation remains useful hardening.

Existing scanners were triaged, not trusted: Bandit 37, Semgrep 6, local installed
backend `pip-audit` 0 known vulnerabilities; no scanner-only finding promoted. Focused
hermetic checks: 52 passed. Three action proposals filed under
`proposals/to-backend/from-backend-audit/`. Auditor changed no source, commit, or remote
state; findings stay OPEN pending independent retest.
