# HANDOFF

## What I did
- Docs-only fix in `docs/suggestions/03-registry.md` (finding R3): corrected the
  stale path reference `config/prompts.py` to its real location
  `registry/config/prompts.py`. Both occurrences were on R3's **Locations** line
  (`:96-121` and `:211-219`).
- Confirmed the real file lives at `backend/registry/config/prompts.py`. The
  other paths in this doc (`handler/support.py`, `store.py`, `schemas.py`, ...)
  are written relative to `backend/registry/capabilities/`, but `prompts.py`
  sits outside that subtree at `backend/registry/config/`, so the bare
  `config/prompts.py` resolved to a nonexistent
  `capabilities/config/prompts.py`. `registry/config/prompts.py` (relative to
  `backend/`) points at the real file and removes the ambiguity.

## What's mid-flight
- Nothing. Single-line documentation change, self-contained.

## What's next
- PR opened from `clannon-bot:docs/registry-prompts-path` into
  `vraksha/Clannon:main`.

## Risks
- None. No code, tests, or contracts touched; pure doc path correction.
- Scope note: the broader path-root inconsistency in this doc (most refs are
  relative to `capabilities/`, this one to `registry/`) was left as-is, since
  the task was narrowly to point the prompts ref at its real location.
