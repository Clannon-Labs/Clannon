# `GET /runs/archive` is listed in ROUTES.md but doesn't exist in the code

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   OPEN
Blocking: no
```

## What this is

Not a feature request — a discrepancy report. While scoping a possible run-history/
archive page, checked what `GET /runs/archive` (listed in `ROUTES.md` under "Runs —
12") actually returns. `grep -rn "archive" backend/api/app.py backend/api/
run_store.py` — zero hits. Searched the rest of `backend/api/*.py` too — nothing.
The route doesn't exist anywhere in the code.

`ROUTES.md` says at its own top: *"Where this file and the code disagree, the code
wins and this file is the bug."* Applying that here rather than building a frontend
page against a route that would always 404 or return nothing.

## What UI this unblocks (if built)

A real run-history view — the sidebar's "Recent" list has no way to see anything
that's been archived/superseded, no filter, no pagination. If "archive" is a real,
intended concept (a run gets superseded on revision — `run_lineage.py` — is that
what this route was meant to surface?), a working version of it would let frontend
build that history page for real instead of guessing at the shape.

## The actual ask

Either:
1. **Build it** — and say what "archived" means (revised-away runs via
   `run_revision.py`'s supersession? Explicitly archived by the user, which would
   need its own `POST`/write path that also doesn't exist yet? Something else?), or
2. **Remove it from `ROUTES.md`** if it was aspirational/never implemented, so the
   table stops listing a route that doesn't serve anything.

Either answer unblocks frontend to plan a real history page around what's actually
there, instead of the current 12-route count including one dead entry.

## How the frontend is coping meanwhile

Not building a history page against this route. If archive/history work happens
before this is resolved, it'll be scoped to what `GET /runs` (which does exist and
already returns full unfiltered summaries) can support client-side.

---

<!-- backend appends below this line; do not edit the section above -->
