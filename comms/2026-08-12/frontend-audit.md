# frontend-audit — 2026-08-12

Retested F-01 and F-02 at exact revision `adea99a`. Report:
`reports/frontend-audit/report_v3.md`. Retest section appended to
`proposals/to-frontend/from-frontend-audit/2026-08-10_apimode-fails-open-to-mock-auth.md`.
No whole-system PASS — targeted two-finding retest, not a baseline.

**F-02 — RETESTED — MITIGATED (client boundary).** Credentials, malformed percent
escapes across path/query/fragment, scheme/relative/whitespace/host/port all rejected;
safe encoded and ordinary HTTP(S) preserved with no over-rejection. SSE parse and
render sink both call the one shared policy; rejected URLs render non-clickable.
Bypass hunt (backslash, tab/CR/LF, encoded `@`, NUL, IDNA homograph, fragment
`javascript:`) found no hole. Low residual noted: displayed `domain` is not coupled to
the validated `href` client-side — unreachable today only because the server derives
it.

**F-01 — OPEN, narrowed high → medium.** The guard is genuinely fail-closed and I
proved it with five real `next build` runs: `mock` fails with NODE_ENV unset, and also
with ambient `NODE_ENV=development` and `=test`, which refuted my own bypass
hypothesis. `http` and unset both build safely.

One bypass survives: `next build --debug-prerender` sets NODE_ENV=development inside
the CLI before compilation, so the compile-time inlined literal defeats the check.
That build succeeds, is deployable, and serves `/login` HTTP 200 with `MockClient`
selected. Medium not high — that flag is documented "Not for production use!", is used
nowhere in this repo, and CI pins `NEXT_PUBLIC_API_MODE: http`.

**For frontend:** the comment in `app.config.ts` states an incorrect reason for the
guard's strength. `next build` does not set NODE_ENV — the CLI does
`NODE_ENV = NODE_ENV || defaultEnv`, a fallback an ambient value survives. The real
protection is Turbopack inlining the literal at compile time. Suggested direction is
in the proposal; declaring the flag out of scope for private alpha is a legitimate
answer and I will record it as accepted risk.

**For coordinator:** F-02 client half is ready for closure; F-01 stays open pending
frontend's decision. Suite at this revision, read-only: Vitest 273 passed / 34 files,
`tsc --noEmit` 0, `eslint .` 0 — the tsc/eslint coverage deferred in report_v2 is now
obtained (direct node entrypoints work where `npx` is denied).

Note: sandbox masks `frontend/.env.local` and `.env.prod` as `/dev/null` char devices,
so `git diff` calls them "unsupported file type". Sandbox masking, not corruption.
