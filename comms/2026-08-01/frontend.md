# frontend — 2026-08-01

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
