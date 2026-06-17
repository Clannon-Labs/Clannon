# experts/ + tools/

**Mostly clean and consistent.** The 9 experts are small, declarative, and follow one
shape: an `@expert` class declaring `domain`/`input_schema`/`output_schema`/`skills`/
`model_role`/`tags` plus `run()` and a `_task()` prompt builder (see `experts/code/expert.py`).
Most are 41-63 lines. Tools self-register via `@tool` and `pkgutil.walk_packages`, so the
extension story is genuinely good (see the trace in [03-registry.md](03-registry.md)).

**File-count to extend (the thing you care about):**
- **Add a tool:** ~1 file — drop a decorated `tools/<name>.py`, it self-registers. No
  other edits.
- **Add an expert:** ~5 files, but they're *inherent* parts of an expert, not accidental
  coupling: `experts/<name>/expert.py` (class + schema + `_task`), `system.md`,
  `skills/*.md`, and the `prompts.secure/experts/<name>/` overlay mirror (`system.md` +
  skills, for production prompt text). Registration itself is automatic.

The two findings are an outlier god-file and the thin per-expert boilerplate.

---

<a id="e1"></a>
## E1 — `media/expert.py` is a 178-line outlier

- **Severity:** Medium
- **Type:** mixed concern
- **Locations:** `experts/media/expert.py` (178) alongside `experts/media/preprocess.py`
  (193); compare to every other expert at 41-63 lines.

**Problem.** The media expert is 3-4× the size of its peers and breaks the "expert.py is a
thin declaration" convention the other 8 follow. It mixes the expert declaration with
substantial media-handling logic (and there's overlap to check against the sibling
`preprocess.py`).

**Why it hurts.** Inconsistency across the roster is itself a maintenance cost — a reader
who's learned the shape from the other 8 experts hits a wall here. The heavy logic in
`expert.py` also isn't reusable by other experts that might want media handling.

**Suggestion.** Push the media-handling logic down into `preprocess.py` (or a
`media/handling.py`), leaving `expert.py` the same thin declaration + `_task` shape as its
peers. Check `expert.py` vs `preprocess.py` for the overlap the size suggests and collapse
it.

---

<a id="e2"></a>
## E2 — `_task` + `run` boilerplate repeated across 8 experts

- **Severity:** Low
- **Type:** duplication (mild)
- **Locations:** the `async def run(self, args, env): … _task(args, env)` pair in each of
  `experts/{code,data_analysis,documentation,notification,summarization,verification,web_research,writer}/expert.py`.

**Problem.** Every expert repeats the same tiny `run()` shell that delegates to a
module-level `_task()` prompt builder. The scaffolding (signature, the call into the env's
`think`, output passthrough) is identical; only `_task`'s prompt text is unique.

**Why it hurts.** Low — the repetition is small and the per-expert uniqueness (the prompt)
genuinely belongs per-expert. But if the `run()` contract ever changes (e.g. a new `env`
capability all experts should use), that's an 8-file edit.

**Suggestion.** Optional. If `run()` is truly identical across experts, a tiny
`PromptExpert` base that implements `run()` and calls a subclass `task(args, env) -> str`
would make the per-expert file just the schema + `task()` + metadata. Only worth it if you
find yourself changing `run()` across experts; otherwise the current explicitness is fine
and arguably clearer. Flagged for awareness, not urgency.

---

## Domain summary

This domain is in good shape and is the proof that the self-registration design works:
adding a tool is one file, and adding an expert touches only the expert's own inherent
parts (code + prompt + skills + overlay) with zero registry wiring. The one real issue is
`media/expert.py` (E1) — a 178-line outlier that breaks the thin-declaration convention the
other 8 experts follow; pushing its logic into `preprocess.py` restores consistency. The
shared `run()` boilerplate (E2) is mild and only worth factoring if the `run()` contract
starts changing across experts.
