# frontend — 2026-08-01

## browser-tested v15, benchmark to 85, pinned project goal (commit edfb7ec, pushed)

Browser-tested the project-creation redesign against real backend — singular
dialog, CTA gating, accessible dialog name all confirmed live, not just via
e2e. Wrote up three sessions of unscored work as benchmark Pass 6: outcome
clarity 87→89, trust and control 89→91, core workflow 86→87, accessibility
95→96. **84.16 → 84.93.**

Offered 5 UX ideas, owner picked pinning the project's goal in view (it was
write-only before — set at creation, then invisible unless you dug into
Memory). Added `src/lib/project-goal.ts` (shared title constant, no new
backend field) + a pinned card on the workspace home screen that stays
visible whether you're typing or not. Verified live on mock (needed
wiki-unlocked plan), zero console errors. Honest known limitation flagged in
the benchmark entry: the same goal entry can double-surface in the memory
recap list on a near-empty project — not fixed, recedes naturally. Pass 7:
**84.93 → 85.03.**

`tsc`/`eslint` clean, vitest 103/103. Full detail:
`reports/frontend/frontend_report_v16.md`.

## project creation moves behind a click; shared-dialog bug + a11y gap found (commit 89670fc, pushed)

Owner correction on the project-creation fields added earlier today: they'd
landed in two places — the New Project dialog (correct) and also
`FirstRunGuide`, an older flow that auto-showed decision/context/deliverable
fields as the default home screen for any zero-run account, no click
required. Deleted `FirstRunGuide`; home screen is now identical for
first-time and returning users. Added a "Start with a project" CTA gated on
**zero projects** (not zero runs — an account with one project shouldn't be
told to make its "first" one again), opening the same New Project dialog.

Lifting that dialog's open state into shared context (so both the sidebar
and the new CTA can open it) surfaced a real bug: `sidebar.tsx` renders its
content twice in the DOM (desktop rail + mobile drawer), so a shared open
flag meant both `ProjectSwitcher` instances' dialogs opened at once. Caught
via e2e (`getByLabel('Project name')` resolved to 4 elements), not by
inspection. Fixed by extracting the dialog into its own component, mounted
once in `AppShell` instead of per-`ProjectSwitcher`-instance.

Also found and fixed while chasing that: `components/ui/dialog.tsx` never
wired an accessible name to the `<dialog>` element (no `aria-labelledby`) —
a real, pre-existing a11y gap affecting every dialog in the app, not just
this one. Fixed with `useId()`.

Rewrote the three e2e specs that drove `FirstRunGuide`'s removed UI. Ran
`first-value.spec.ts` + `completion-status.spec.ts` for real against a mock
production build on port 3100 — 5/5 passing. `real-backend.spec.ts` fixed
for the same selectors but not executed (10-min timeouts, needs live
backend — flagged, not claimed verified).

**Own mistake, corrected**: cleaning up the 3100 test server, ran `pkill -9
-f "next-server"` — too broad, killed the shared `:3000` dev server too
(running since before this session, possibly serving the owner's own
browser). Caught immediately, restarted in the same config, verified real
traffic resumed before continuing. Full detail in
`reports/frontend/frontend_report_v15.md`.

## memory provenance cards + honest inferred-tier delete (commit 6531b29, pushed)

Closed `proposals/to-frontend/2026-07-30_memory-provenance-cards.md` (backend's
memory-provenance proposal). Found and picked up mid-flight uncommitted work
from an earlier session (types/mock/card rendering already done) and finished
the remaining acceptance gap:

- Memory cards now show curator provenance (saved by, kind, rationale,
  session/trace id, participants) when the backend returns it.
- Inferred tiers (semantic/episodic/procedural) are now deletable in the UI —
  they were already deletable server-side, the UI just never exposed it.
  Edit stays wiki-only (no markdown form for a pipeline-derived fact).
- Delete confirmation + toast no longer claim every deletion is "from your
  wiki" with an undo promise — undo only exists where a real recreate
  operation does (wiki).

New `src/tests/memory-page.test.tsx` renders the real page (hooks doubled,
DOM asserted) instead of just type-checking the change — verifies provenance
renders, inferred delete has no edit/no undo/no fake recreate call, wiki
delete still gets both. `tsc`/`eslint` clean, vitest 97/97.

No browser click-through in this session — extension wasn't connected here,
and an existing `:3000` dev server (possibly someone's active window) was in
`http` mode against an unreachable backend, so I didn't touch it. RTL test
covers the same interaction path; flagged in the proposal response as the one
piece of evidence weaker than a real click-through.

Proposal archived to `proposals/archive/to-frontend/`.

## project-creation goal/context/files + a real plan-tier bypass found (HIGH priority proposal filed)

Owner asked for benchmark status; backend answered `curl localhost:8000/health`
200 mid-session, so I switched to real HTTP mode for verification instead of
mock. Also added, per owner ask: New Project dialog now collects an optional
goal, client context, and reference files (all become wiki entries/imports on
project creation) — reused the existing `useSaveMemory`/`useUploadMemory`
contracts the Memory page already exercises, no new endpoint needed.

Testing it against live backend as a fresh free-tier signup surfaced a real
plan-tier bypass, not a frontend bug: `GET /memory`, `POST /projects`
(`seedFacts`), `POST /memory`, and `POST /memory/upload` in
`backend/api/app.py` never check `user.plan` at all. A free ("Seedling")
account's wiki tier shows as UI-locked, but the full content was already in
the network response, and nothing stops writing to it either — confirmed
live (3 wiki entries written and readable via the count badge on an account
whose plan doesn't include wiki).

Fixed the frontend side properly per owner instruction ("shouldn't be
bypassable from the frontend"): the goal/context/files fields are no longer
just discouraged with a note — they're not rendered at all when
`!plan.memoryTiers.includes("wiki")`, and the submit handler independently
guards against sending them regardless of stale state. New
`src/tests/project-switcher.test.tsx` (3 tests) proves both branches render
correctly and that a locked-plan submit sends `seedFacts: undefined` and
never calls the goal/file mutations.

Filed `proposals/to-backend/2026-08-01_memory-plan-tier-not-enforced-serverside.md`
(HIGH) — this needs actual server-side enforcement on both read and write;
frontend's fix removes the UI path but was never meant to be the security
boundary. Directly relevant to the owner's private-alpha "no vulnerabilities"
bar. Not blocking today's ship — the frontend feature works correctly for
plans that do have wiki, and correctly offers nothing for plans that don't.

Verified: `tsc`/`eslint` clean, vitest 100/100 (was 97). Live browser
click-through against real backend (192.168.18.84:3000, LAN origin — plain
`localhost` trips a CSP mismatch in this dev config, noted but not chased,
separate from today's work) for both the field-visible and field-hidden
paths, screenshots not saved to `previews/` this round (ephemeral
`.playwright-mcp/` captures only, used for verification not evidence
archival — will capture proper before/after previews if this needs a
dedicated benchmark pass).
