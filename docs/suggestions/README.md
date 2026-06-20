# Backend modularity & maintainability audit

Date: 2026-06-17 · Scope: `backend/` only · Lens: **maintainability / modularity**, not
correctness, security strength, or test coverage (those have their own review paths).

This is an architecture-review pass over the whole backend (~13k LOC) looking for the
things you asked about:

- **redundancy** — the same logic written in more than one place;
- **non-modular code** that could be a clean, reusable seam;
- **god-files / mixed concerns** — one file (or function) doing several unrelated jobs;
- **scattered logic** — one concept whose definition is spread across many files, so a
  change means hunting;
- **change-amplifying coupling** — "to change behaviour X I must edit N files."

Findings are split by domain (one file each) plus a cross-cutting file for issues that
span domains. Every finding carries `file:line`, a severity, the maintenance cost, and a
concrete fix. The high-severity findings were all verified first-hand against the code.

> **Update (2026-06):** Acted on since this audit. The Stage-metadata + runs.py-split refactor
> implemented **X1** (pipeline driven 3 ways + parallel side-arrays) and **A3** (`runs.py`
> god-file) as recommended: `_STAGE_LABELS`/`_STAGE_STATUS` are gone (label/status now live ON
> each `Stage` in `core/pipeline.py`), both entry points call the unified
> `pipeline.run(on_stage=...)`, and `api/runs.py` is now a thin façade over
> `api/run_{state,store,driver}.py` + `api/sse.py`. The X1 and A3 pages and the F2
> stage-identity paragraph carry dated notes with specifics. Other findings (e.g. the
> `Origin`/`PipelineStage` enums in F2) and the historical analysis below are left intact.

## The headline, up front

You gave one concrete fear: *"I don't want to edit multiple files just to make the
orchestrator call experts with an extra argument."*

**Good news: that exact scenario is already a one-file edit.** The capability path is
fully schema-driven end to end — `args.model_dump()` → an opaque `arguments` dict →
`input_schema(**arguments)`, and the JSON Schema is auto-advertised to the model. Adding
an argument means adding one field to the expert's own input model in
`experts/<name>/expert.py` and consuming it. **Zero registry files change.** Dropping a
new expert or tool file self-registers via `pkgutil.walk_packages` — no hand-maintained
list. The registration layer is the *clean* part of the codebase.

The real change-amplifying coupling lives elsewhere, and that's what this report is
about. The worst offender is the **pipeline driver**: the same "walk the stages" loop is
written three times, two of them with a hand-synced parallel array — so adding or
reordering a stage today *does* mean editing several files.

## Severity-ranked findings

| # | Finding | Domain | Sev | Type |
|---|---------|--------|-----|------|
| [X1](00-cross-cutting.md#x1) | Pipeline driven 3 different ways + parallel stage side-arrays | cross-cutting | **High** | dup + coupling |
| [X2](00-cross-cutting.md#x2) | `_ObservedLog` duplicated verbatim | cross-cutting | Med | dup |
| [S1](02-security-sanitizers.md#s1) | `_highest_threat` + `_run_worker` copy-pasted across 4 workers | security | **High** | dup |
| [S2](02-security-sanitizers.md#s2) | `audio.py` ≈ `video.py` (~60% identical) | security | **High** | dup |
| [S3](02-security-sanitizers.md#s3) | Modality→worker binding is a hardcoded `if` ladder | security | Med | coupling |
| [A1](01-api-delivery.md#a1) | Run/SSE state shape spread across 5 sites | api | **High** | scattered |
| [A2](01-api-delivery.md#a2) | `app.py` runs inline wiki SQL via `auth._db()` | api | **High** | mixed concern |
| [A3](01-api-delivery.md#a3) | `runs.py` is a 591-line god-file | api | Med | mixed concern |
| [R1](03-registry.md#r1) | `support.py` god-file: 4 unrelated concerns | registry | Med | mixed concern |
| [R2](03-registry.md#r2) | 3 near-identical tool/expert wrapper factories | registry | Med | dup |
| [C1](04-core.md#c1) | Two independent provider-failure classifiers | core | Med | dup |
| [C2](04-core.md#c2) | Per-layer bounds as parallel `if layer ==` chains | core | Med | dup |
| [C3](04-core.md#c3) | Episodic write-policy hardcoded in the orchestrator | core | Med | scattered |
| [F1](05-foundation.md#f1) | `__init__.py` triple-declaration tax | foundation | Med | coupling |
| [F2](05-foundation.md#f2) | `Origin` / `PipelineStage` parallel enums | foundation | Med | scattered |
| [E1](06-experts-tools.md#e1) | `media/expert.py` is a 178-line outlier | experts | Med | mixed concern |
| [R3](03-registry.md#r3) | Overlay precedence re-implemented in `_load_one` | registry | Low | dup |
| [R4](03-registry.md#r4) | `catalog()` vs `cards()`; `wants_*` not on the spec | registry | Low | dup + coupling |
| [R5](03-registry.md#r5) | `PermissionLevel.NETWORK` special-cased inline | registry | Low | scattered |
| [C4](04-core.md#c4) | `MemoryManager` mixes 5 concerns | core | Low | mixed concern |
| [C5](04-core.md#c5) | `memory/writer.py` misnamed (only distills) | core | Low | naming |
| [C6](04-core.md#c6) | Verifier consistency-coercion scattered | core | Low | scattered |
| [E2](06-experts-tools.md#e2) | `_task` + `run` boilerplate repeated 8× | experts | Low | dup |
| [F3](05-foundation.md#f3) | Docstring/constant drift (unused + wrong) | foundation | Low | drift |

## Cross-cutting themes

Three patterns recur and are worth fixing as *patterns*, not one finding at a time:

1. **Parallel arrays / parallel `if`-ladders keyed on the same thing.** `ACTIVE_STAGES`
   has two sibling label/status arrays (X1); model bounds are two `if layer ==` ladders
   (C2); modality dispatch is an `if modality in` ladder (S3). Each pair drifts silently
   because nothing ties the entries together. Fix shape: make the *thing* carry its own
   metadata (a stage is a `(fn, label, status)` record; a layer is a config row), so
   there is one list to edit.

2. **Copy-paste-then-rename.** The sanitizer workers (S1/S2), the wrapper factories
   (R2), and `_ObservedLog` (X2) are all "I needed another one like this, so I copied
   it." Each copy is a place a future fix has to be re-applied by hand. Fix shape: a
   small shared base/helper that the variants parameterise.

3. **Logic that drifted into the wrong layer.** Wiki SQL in `app.py` instead of `auth`
   (A2); episodic write policy in the orchestrator instead of `memory` (C3); the serialized
   run shape smeared across the store instead of owned by one (de)serializer (A1). Fix
   shape: move the logic to the module that owns the concept, expose one function.

## Suggested fix order

Ranked by (impact on your stated pain) ÷ (effort). None of these are urgent — the system
runs end to end. This is debt to pay down deliberately, ideally before the cloud build
adds more callers on top of these seams.

1. **X1 — unify the pipeline driver.** Highest leverage. Give `core.pipeline.run` an
   optional per-stage observer hook + a decision-log sink; have `main.py` and
   `api/runs.py` pass callbacks instead of re-walking the stages. Kills X1, X2, and the
   two parallel side-arrays at once. ~half a day.
2. **S1/S2/S3 — factor the sanitizer workers.** A `workers/_base.py` with the shared
   `_highest_threat`/`_run_worker`/result-merge, an `ffmpeg`-backed base for audio+video,
   and a single `MODALITY_WORKERS` map the runner iterates. ~1 day.
3. **A1/A2/A3 — split the API surface.** Move wiki persistence into `auth` (A2), give
   `RunState` one `to_row`/`from_row` pair (A1), peel `runs.py` into store / driver / SSE
   (A3). ~1 day.
4. **R1/R2 — split `support.py` and collapse the factories.** ~half a day.
5. The Medium/Low core + foundation items as you next touch those files.

Read the per-domain files for the detail behind each row.
