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
