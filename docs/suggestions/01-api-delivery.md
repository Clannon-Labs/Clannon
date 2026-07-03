# api/ + delivery/ + main.py

`api/runs.py` (591) and `api/app.py` (505) are the two largest files in the backend, and
both mix concerns. The shared root cause across this domain: there is no single primitive
for "drive the pipeline while observing it and persist the result," so each entry point
reinvents pieces of it. (The cross-cutting half of that — the stage loop and `_ObservedLog`
— is written up as [X1](00-cross-cutting.md#x1)/[X2](00-cross-cutting.md#x2).)

---

<a id="a1"></a>
## A1 — The run/SSE state shape is spread across 5 sites

- **Severity:** High
- **Type:** scattered logic
- **Locations:** `api/runs.py` — `class RunState` (`:120`), `full_json()` (`:240`),
  `persist()` INSERT (`:311`), `_from_row()` (`:332`), plus the `CREATE TABLE`/`ALTER`
  schema in the same file.

**Problem.** A run's shape is defined five times: the in-memory dataclass fields, the
`full_json()` serializer the API returns, the `INSERT` column list in `persist()`, the
`_from_row()` deserializer, and the table DDL. To add **one** field to a run (say
`token_cost`) you must edit all five in lockstep, and nothing checks that they agree.

**Why it hurts.** This is the "edit N files (or N functions) to change one thing" pain,
concentrated in the most-touched API object. The audit already found drift here: the SSE
event union is hand-mirrored against the frontend's `types.ts` with no enforcement, and
`sources`/`usage` had already diverged. Field additions are routine as the product grows;
each one is a five-way coordinated edit waiting to miss a spot.

**Suggestion.** Make `RunState` own exactly one `to_row()` / `from_row()` pair and derive
the JSON from the same place (or make the persisted row *be* the JSON: store one
`payload` JSON column + the few columns you actually query/filter on, e.g. `id`,
`user_id`, `status`, `created_at`). Then "add a field" = add it to the dataclass; the
serializer and persistence follow because they iterate fields, not a hand-written column
list. For the SSE↔frontend contract, generate or snapshot-test the event shape against
`types.ts` so drift fails a test instead of reaching the browser.

---

<a id="a2"></a>
## A2 — `app.py` runs inline wiki SQL by reaching into `auth._db()`

- **Severity:** High
- **Type:** mixed concern / leaky abstraction
- **Locations:** `api/app.py:316, 344, 355, 381, 409` — `with auth._db() as db:` + raw
  `SELECT/INSERT/UPDATE/DELETE` against `wiki_entries` (and similar for model prefs).

**Problem.** The route layer reaches into a **private** member of the auth module
(`auth._db()`) and runs hand-written SQL for wiki CRUD in five places. Persistence logic
lives in the routing file.

**Why it hurts.** Your own `api/CLAUDE.md` states the property this breaks: *"`auth.py` is
the dev stand-in for Supabase … swap this ONE module when Supabase lands."* Right now the
Supabase swap would **not** be one module — you'd also have to find and rewrite every
`auth._db()` + raw-SQL block scattered through `app.py`. It also defeats the
`SET LOCAL`-per-transaction RLS plan the same file mandates: RLS scoping has to live where
the queries live, and the queries are in the wrong place. And `app.py` stops being "routes
+ CORS" (as the CLAUDE.md says it should be) and becomes a data-access file too.

**Suggestion.** Give `auth` (or a sibling `store`/`repo` module) a small typed API:
`fetch_wiki(user_id)`, `create_wiki(user_id, …)`, `update_wiki(...)`, `delete_wiki(...)`,
and the same for model prefs. `app.py` calls those and never touches `_db()` or SQL. The
Supabase migration becomes the one-module swap the doc promises, and RLS scoping has a
single home. (`auth.fetch_wiki` is already used by `runs.py:499` — so the pattern exists;
the `app.py` routes just bypass it.)

---

<a id="a3"></a>
## A3 — `runs.py` is a 591-line god-file (store + driver + SSE + recovery)

> **Update (2026-06):** Superseded by the runs.py-split refactor, which split along the
> exact seams this finding named. `api/runs.py` is now a ~40-line façade that only
> re-exports; the four jobs moved to focused modules: `api/run_state.py` (`RunState` + its
> serialization), `api/run_store.py` (`RunStore`, `STORE`, in-memory cache + SQLite
> persistence), `api/run_driver.py` (`execute`/`_drive`, model-override resolution,
> conversation replay), and `api/sse.py` (`sse_stream`). Filter-block recovery is no longer
> here either: it moved to the single shared `core.pipeline.recover_from_filter_block`. The
> historical analysis below is left intact.

- **Severity:** Medium
- **Type:** mixed concern
- **Locations:** `api/runs.py` — `RunState` + `RunStore` (in-memory + SQLite persistence),
  `execute()`/`_drive()` (pipeline driving), the SSE event construction, `model_overrides`
  application, and `_recover_from_filter_block()` all in one module.

**Problem.** One file owns at least four jobs with different reasons to change: (1) the
run data model + its persistence, (2) driving the pipeline, (3) building the SSE event
stream, (4) the filter-block recovery policy. They're interleaved, so understanding any
one means scrolling past the others.

**Why it hurts.** It's the single most-edited server file and the hardest to reason about;
every new endpoint behaviour lands here and grows it. Mixed concerns also make A1 worse
(the shape is buried among unrelated code) and make testing the driver in isolation hard.

**Suggestion.** Split along the seams that already exist in the code:
`run_store.py` (`RunState` + `RunStore` + the `to_row`/`from_row` from A1),
`run_driver.py` (`execute`/`_drive` — ideally a thin caller of the unified
`pipeline.run` from [X1](00-cross-cutting.md#x1) plus the filter-block recovery),
and `sse.py` (event construction + the typed event union from A1). `app.py` keeps the
routes. None of these is a behaviour change — it's moving cohesive blocks into named
files.

---

## Domain summary

The two High items both trace to logic sitting in the wrong place: the run *shape* is
smeared across five sites instead of owned by one (de)serializer (A1), and wiki
*persistence* lives in the routing file instead of the swappable auth module (A2) —
directly contradicting the "swap one module for Supabase" property your own CLAUDE.md
promises. Both, plus the god-file (A3), get much smaller once the cross-cutting pipeline
driver (X1) gives `runs.py` a single `pipeline.run(on_stage=…)` to call instead of its own
stage loop. Fixing A2 first is cheap and unblocks the cloud migration story.
