# Real Backend Paid-User Journey

Date: 2026-07-28  
Frontend: Next 16.2.12 dev build, `7ff1ca7` plus dirty frontend worktree  
API: isolated backend at `http://localhost:8000`, `/ready` healthy  
Browser: system Google Chrome through Playwright

## Exercised

- Fresh desktop signup and truthful empty workspace.
- Guided project, decision, context, and deliverable intake.
- Project memory and model-settings inspection before send.
- Return to workspace with exact prepared brief restored.
- Small PNG attachment, real run submission, live status, decision log, Stop,
  route departure, reload, and reconnect.
- Typed follow-up recovery within same browser tab.
- Terminal recovery through login and direct run history after server time.
- Partial-verification state, token usage, copy/download controls, and very long
  report reading.
- Fresh signup and Memory navigation at 390×844.

## Frontend defects found and fixed

1. Prepared onboarding brief vanished after Memory/Settings navigation.
   Workspace drafts are now user/project scoped, expire after 24 hours, survive
   route changes/reload in the tab, and degrade to memory when storage is blocked.
2. Live composer promised typed text would send automatically after completion,
   but no queue existed. Copy now says Send unlocks after completion; reply text
   survives same-tab reload without claiming it is queued.
3. Long delivered reports lost verification/export controls after first screen.
   Report masthead now stays pinned while reading.

## Real outcome

Run `run_16cac313852a` recovered after navigation and restart. Attachment,
brief, status, report, and usage persisted. UI remained coherent.

Backend execution exceeded four minutes, consumed 284.3k tokens, then marked
the run `delivered` while report itself said it could not finish within allowed
time. Result was honestly labelled partially verified, but `DELIVERED` conflicts
with user-visible partial timeout. Backend contract proposal records this.

## Proof

- `previews/2026-07-28_real-backend-pass/`
- Desktop resume/recovery Playwright: 1/1 pass.
- Mobile real signup/navigation Playwright: passed during original journey.
- Landing keyboard/theme behavior Playwright: 1/1 pass.
- Chrome DevTools MCP was available but could not launch without X server.
  System Chrome through Playwright supplied browser, screenshot, console, and
  interaction proof instead.

## Limits

- OAuth and Stripe unavailable by backend contract.
- No claim-level correction/share/version workflow.
- Full mobile live run to terminal was not repeated; desktop run already used
  backend maximum execution window.
- Real timeout requires structured backend terminal semantics before frontend
  can label it without parsing report prose.
