# foundation/ (transport, vocab, contracts)

**Genuinely clean.** The god-file suspects all hold up as single cohesive concerns:
`transport/flow.py` (667) is one thing (the Flow transport), `transport/context.py` (421)
is one thing (the run context), `vocab/errors.py` (327) is one thing (the error taxonomy).
None is a dumping ground. The contracts are properly thin ports. The findings here are a
re-export tax, one parallel-enum pair, and some doc drift — no invented problems.

---

<a id="f1"></a>
## F1 — `__init__.py` triple-declaration tax

- **Severity:** Medium
- **Type:** change-amplifying coupling
- **Locations:** `foundation/__init__.py:11-152`.

**Problem.** Every public symbol is declared three times: at its definition, in the import
block (`:11-80`), and again in the 70-line `__all__` literal (`:82-152`). Adding one error
type or one contract means editing the definition plus two hand-maintained lists in this
file.

**Why it hurts.** This is the "edit multiple places for one change" pattern, on the most
imported module in the backend. The import block and `__all__` *will* drift — a symbol
imported but missing from `__all__`, or vice versa — and nothing catches it.

**Suggestion.** Drop the redundant `__all__` literal and derive it, or (cleaner) keep
`__all__` but generate it from the imported names at import time (`__all__ = [n for n in
globals() if not n.startswith("_")]` after the imports, or an explicit
`__all__ = [*_transport, *_errors, …]` built from per-bucket lists). Either way there's one
list to maintain, not two. The import lines themselves are unavoidable; the duplicate
`__all__` is the removable half.

---

<a id="f2"></a>
## F2 — `Origin` and `PipelineStage` are parallel enums for the same concept

> **Update (2026-06):** Partially superseded. The `_STAGE_LABELS`/`_STAGE_STATUS` side-arrays
> named in "Why it hurts" below were removed by the Stage-metadata refactor (label and status
> now live ON each `Stage` in `core/pipeline.py`), so a stage's identity is no longer spread
> across those two arrays. But the actual finding still stands: `Origin` (`vocab/types.py:26`)
> and `PipelineStage` (`transport/context.py:65`) BOTH still exist with the same mismatched
> value strings. Only the side-array half of the "spread across N places" sentence is stale.

- **Severity:** Medium
- **Type:** scattered logic
- **Locations:** `vocab/types.py:26-43` (`Origin`) and `transport/context.py:65-83`
  (`PipelineStage`).

**Problem.** Two enums name the same set of pipeline stages, in two files, with
**deliberately mismatched** value strings (e.g. `"sanitizer"` vs `"sanitizing"`) and no
link between them.

**Why it hurts.** "What are the pipeline stages?" has two answers that must be kept in sync
by hand, and the value-string mismatch is a trap: code that maps one to the other relies on
remembering the off-by-a-suffix difference. Add a stage and you update two enums in two
files (and recall they disagree on spelling). Compounds the X1 stage-array problem — a
stage's identity is now spread across `ACTIVE_STAGES`, `_STAGE_LABELS`, `_STAGE_STATUS`,
`Origin`, *and* `PipelineStage`.

**Suggestion.** Pick one enum as the source of stage identity and derive the other's
display/origin string from it (or merge them). If they must stay separate (one is
"who produced this" vs one is "what phase are we in"), give each member of one an explicit
link to the other rather than relying on string proximity. Tie this to the X1 fix so the
"set of stages" lives in exactly one place.

---

<a id="f3"></a>
## F3 — Docstring / constant drift

- **Severity:** Low
- **Type:** drift
- **Locations:** various in `vocab/errors.py`, `vocab/constants.py`, `vocab/types.py`.

**Problem.** Small truths that have gone stale:
- Three error docstrings reference constants that don't exist (`MAX_INPUT_TOKENS`,
  `MAX_FILTER_RETRIES`, `MAX_TOOL_RETRIES`).
- `SPAN_ID_LENGTH` / `TRACE_ID_LENGTH` are defined but never used — three call sites
  hardcode `uuid4().hex[:8]` instead.
- `BlockReason`'s docstring omits the `MALFORMED_INPUT` member it defines.
- `MemoryStore`'s docstring contradicts itself on the `WORKING` tier (says 4 durable tiers,
  lists 5 members).

**Why it hurts.** Each is a small "the comment lies" papercut that erodes trust in the
docs and, for the unused constants, hides that the intended abstraction (named ID lengths)
was bypassed.

**Suggestion.** Either use `SPAN_ID_LENGTH`/`TRACE_ID_LENGTH` at the three `uuid4().hex[:8]`
sites or delete them; fix the four docstrings to match the code. Five-minute cleanup.

---

## Domain summary

Foundation is the cleanest domain — the large files are large because their concern is
large, not because they're mixed. The one structural item worth acting on is the
`__init__.py` re-export tax (F1): the duplicate `__all__` literal doubles the edit cost of
every new public symbol and will drift from the import block. The `Origin`/`PipelineStage`
parallel enums (F2) are the same "pipeline stages defined in N places" theme as X1 and
should be folded into that fix. F3 is trivial doc hygiene.
