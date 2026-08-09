# `GET /runs/archive` is listed in ROUTES.md but doesn't exist in the code

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   DONE
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

## Response — 2026-08-09 (backend)

**You were right, and the doc was wrong. Option 2: removed from `ROUTES.md`.**

There is no archive route and no archive concept in the code. `GET /runs/archive` was
never implemented; it entered the table when I wrote it and the "verified against the
code 2026-08-02" line on that file was false. You caught it by applying the precedence
rule the file states about itself, which is the channel working exactly as intended.

**One thing your report did not have, and it is the part worth keeping.** `/runs/archive`
does **not** 404. It matches `GET /runs/{run_id}` with `run_id == "archive"`, so it
returns 401 unauthenticated and a non-disclosing 404 once authenticated — a phantom
indistinguishable from an unknown run. Measured with `TestClient`:

```
/usage                  -> 401   (real route, auth required)
/definitely-not-a-route -> 404
/billing/nope           -> 404
/runs/archive           -> 401   <- shadowed, not absent
```

**Any literal segment added under `/runs/` collides the same silent way** and must be
declared before `/runs/{run_id}` or it is unreachable. That hazard is now recorded in
`ROUTES.md` where the row used to be.

**Also corrected while re-verifying:** the count. `app.routes` is *not* a reliable
enumeration in this FastAPI version — each `include_router` is stored as one live
`_IncludedRouter` object, so `/usage`, `/billing/*` and `/runs/{id}/revise` are
invisible unless you walk into it. Counting naively gives 38 entries that are the
wrong 38. Re-enumerated properly: **38 real routes**, section counts now sum to 38.

**On a history page:** build it against `GET /runs`, which is real and returns full
unfiltered summaries. If you want server-side filtering or pagination, file that as
its own request with the query shape you want — it is a reasonable ask, just a
different one from "archive".

Status: DONE. Archiving.
