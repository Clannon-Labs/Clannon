# frontend — 2026-08-10

## Signup was wrong against the already-shipped waitlist gate — fixed, plus two 404s a real user would have hit

Not a premium-gap pass. The private-alpha waitlist backend shipped 2026-08-09
(`97dfdb7`, `config/backend/waitlist.yaml` ships `enabled: true`), but `/signup` was
still the old open form and `/waitlist/confirmed` / `/waitlist/invalid-link` — the two
routes `verify_waitlist` redirects real visitors to — didn't exist. A real email
verification would have succeeded server-side and 404'd in the browser.

Filed `specification/api/requests/2026-08-10_config-waitlist-enabled-flag.md` first
(one field, `GET /config` → `waitlistEnabled`) then built regardless, per the mock-first
policy. `/signup` now branches on `?approvalToken=` presence and the flag, failing
closed (gated) on every unknown state since the committed backend default already is
`true`. Built `/waitlist` (join), `/waitlist/confirmed`, `/waitlist/invalid-link`.
`MockClient.signup()` now enforces the same gate `app.py` does.

Verified: tsc/eslint clean, Vitest 227/227 (26 new, gate mutation-checked), production
build, curl-verified all six route/state combinations serve 200 with correct body text.
**Playwright/Chrome-DevTools MCP was disconnected this session — no real browser
click-through, flagged explicitly in the report and benchmark log, not silently
skipped.** No score claimed (Pass 16 in the benchmark file) — catch-up fix, not new
capability, and unexercised-in-browser per this file's own rule.

Full detail: `reports/frontend/frontend_report_v25.md`.

## Follow-up, same day — waitlist browser pass done, plugin connection fixed

MCP tools came back mid-session (marketplace cache was stale for all 4 plugins,
`claude plugin marketplace update` + `/reload-plugins` fixed it — not a per-plugin
reinstall). Did the browser pass Pass 16 flagged as missing: 9 states, desktop +
mobile 390px, zero console errors, zero overflow. Approved-signup path verified
end to end into a real `/app` landing with a genuinely empty first-run state. No
bugs found, no code changes, no score move (same reasoning as Pass 16 — catch-up
fix, not new capability). `frontend_report_v26.md`,
`previews/2026-08-10_waitlist-browser-pass/`.
