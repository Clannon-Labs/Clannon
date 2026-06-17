# registry/

**This is the domain you were most worried about, and it is the cleanest one.** Your fear
— "edit multiple files to let the orchestrator call experts with an extra argument" — does
not happen here. The trace below proves it. The real registry findings are a god-file and
some wrapper duplication, both Medium, plus minor items.

---

## The "extra argument" trace (your stated pain)

Scenario: the orchestrator should pass one extra argument (say `depth: int`) when it
spawns an expert. Tracing the actual data path:

1. `handler/support.py:332` — `_make_orchestrator_expert_fn`'s parameter type **is** the
   expert's `input_schema` (`args: input_schema`). It serializes with
   `args.model_dump()` (`:334`) into `ExpertRequest(key, arguments=…)`. No field names
   appear.
2. `schemas.py` — `ExpertRequest.arguments` is `dict[str, Any]`. Opaque bag. No change.
3. `handler/experts.py:60` — rebuilds the instance generically:
   `args = spec.input_schema(**request.arguments)`, then `spec.impl().run(args, env)`. No
   field named.
4. `store.py:72` — `cards()` emits `input_schema.model_json_schema()`, so the new field is
   **automatically advertised** to the orchestrator model as a tool parameter.

**Files inside `registry/` that change to add the argument: zero.** The only edit is the
expert's own input model in `experts/<name>/expert.py` (add the field, consume it in
`_task`). The seam you wanted already exists — the per-capability `input_schema` *is* the
contract, round-tripped as an opaque dict. Likewise, `discover()` uses
`pkgutil.walk_packages` (`registration.py:98`), so dropping a decorated file
self-registers with no list to maintain. Adding a tool = one file. Adding an expert = the
expert's own package (code + prompt + skills), which is inherent, not registry coupling.

---

<a id="r1"></a>
## R1 — `support.py` is a 357-line god-file mixing 4 unrelated concerns

- **Severity:** Medium
- **Type:** mixed concern
- **Locations:** `handler/support.py` — overlay resolution (`:40-60`), skills
  parsing/`SkillBook` (`:67-146`), **expert** agent assembly (`:149-292`), and
  **orchestrator** agent assembly (`:303-357`).

**Problem.** The file's name and docstring describe only the expert runtime ("the
tool-driving environment an expert runs in"), yet it also owns the entire *orchestrator*
agent-assembly path (`OrchestratorDeps` + both native-tool factories +
`build_orchestrator_tools`), plus skill-file frontmatter parsing, plus the prompt-overlay
re-wrap. Four concerns with four different reasons to change.

**Why it hurts.** Someone changing orchestrator tool-wrapping has to open a file
documented for experts. The whole file is also forced to skip
`from __future__ import annotations` (`:16-18`, needed for the dynamic `input_schema`
annotation in the wrappers) — a constraint that then applies to the skills parser and
orchestrator code that don't need it. It's the same "edit-the-wrong-thing" surface you
dislike, inside one file.

**Suggestion.** Split by concern: `skills.py` (`_parse_skill`, `_Skill`, `SkillBook`,
`skills_hint`); keep an expert-runtime file (`ExpertEnv`/`ExpertDeps`/`ScopedToolbox`/
`build_expert_tools`/`think`); move orchestrator assembly into `capability.py` (its only
caller, `capability.py:81`) or a new `orchestrator_runtime.py`. The shared wrapper helper
from R2 lands where both can import it.

---

<a id="r2"></a>
## R2 — Three near-identical wrapper factories

- **Severity:** Medium
- **Type:** duplication
- **Locations:** `handler/support.py:191` (`_make_tool_fn`), `:311`
  (`_make_orchestrator_tool_fn`), `:326` (`_make_orchestrator_expert_fn`).

**Problem.** All three follow the same closure pattern: define an inner `async def`, set
`.__name__ = key.replace(".", "_")` and `.__doc__ = description`, route through a handler,
return the result. `_make_tool_fn` and `_make_orchestrator_tool_fn` are nearly
line-for-line identical — the only real differences are the `RunContext[...]` deps type
and whether the call goes through `ScopedToolbox.call` vs `handler.call_tool(ToolRequest…)`
(and `ScopedToolbox` at `:149-158` is itself a 2-line shim over the same `call_tool`). The
expert variant differs more (it formats a `finding_ref`/summary string) but repeats the
same name/doc/closure scaffolding.

**Why it hurts.** Any change to the wrapper convention (per-call tracing, how a tool error
is surfaced to the model, the name-mangling rule) must be made in three places and synced
by hand. Two factories wrapping the *same* `ToolHandler.call_tool` contract is the clearest
accidental duplication.

**Suggestion.** Collapse to one `_make_wrapper(key, input_schema, description, *, invoke)`
where `invoke(ctx, args) -> result` is the only varying piece and a tiny helper sets
`.__name__`/`.__doc__`. The three variants become three short `invoke` closures.
Unify the tool-call path so there's one invocation seam, not `ScopedToolbox` plus an inline
copy.

---

<a id="r3"></a>
## R3 — Overlay precedence re-implemented inside `_load_one`

- **Severity:** Low
- **Type:** duplication
- **Locations:** `config/prompts.py:96-121` (`resolve_overlay`/`read_overlay_text`, the
  real helpers) vs `config/prompts.py:211-219` (the inline "overlay / relative + is_file()
  + source tag" block in `PromptRegistry._load_one`).

**Problem.** The "overlay file wins, committed baseline falls back" rule is encapsulated in
`resolve_overlay`, but `_load_one` re-derives it inline instead of calling it. (The
expert-side helpers `_overlaid`/`_expert_overlay_rel` in `support.py` *do* delegate
correctly, so they're fine.)

**Why it hurts.** Overlay precedence is a security-relevant invariant (per the registry
`CLAUDE.md`: the overlay supplies content only). Written twice, a future change to the rule
(new search root, case-insensitive lookup) can land in one path and be missed in the other.

**Suggestion.** Have `_load_one` call `resolve_overlay(...)` so there is exactly one
overlay-precedence implementation.

---

<a id="r4"></a>
## R4 — `catalog()` vs `cards()` overlap, and `wants_*` traits aren't on the spec

- **Severity:** Low
- **Type:** duplication + coupling
- **Locations:** `store.py:46` (`catalog`), `store.py:54` (`cards`); impl-trait reads via
  `getattr(s.impl, "wants_workspace", False)` at `capability.py:88` and `experts.py:115`.

**Problem.** "What metadata describes a capability for consumers (UI/orchestrator)" is
expressed twice — `catalog()` (key/description/domain/tags) and `cards()` (a superset
adding permission + input JSON-Schema + status). Meanwhile runtime traits that *are*
metadata (`wants_workspace`, `wants_memory`) live as `getattr` on the impl class, not on
`CapabilitySpec`, so they never reach `cards()` and must be re-derived by `getattr` at two
sites.

**Why it hurts.** Cuts against your stated Expert→UI goal ("editing an expert auto-updates
what the UI can render"). A field on the class is *not* automatically in the card; impl
traits aren't surfaced at all. Two metadata methods to keep consistent.

**Suggestion.** Make `CapabilitySpec` the single source: lift `wants_workspace`/
`wants_memory` onto the spec at registration (the decorators already `getattr` other
fields), and make `catalog()` a projection of `cards()` rather than a separate dict. Then
"new UI metadata" = add a field to the spec + decorator, and it flows to the card.

---

<a id="r5"></a>
## R5 — `PermissionLevel.NETWORK` special-cased inline

- **Severity:** Low
- **Type:** scattered logic
- **Locations:** `handler/tools.py:82-83` (grant check), `:110`
  (`if spec.permission == PermissionLevel.NETWORK` → triggers invariant-A re-sanitization),
  `handler/experts.py:132-134` (grant-set assembly).

**Problem.** Permission *semantics* aren't centralized: the "NETWORK output must be
re-sanitized" rule is an inline `==` literal in `tools.py:110`, far from where grants are
defined. A new level (`WRITE`, `FILESYSTEM`, …) means hunting these scattered checks.

**Why it hurts.** The same multi-file-edit shape, applied to permissions. Behaviour is
coupled to one enum member by string-equality at a distance.

**Suggestion.** Within this domain, hoist "does this permission require output
sanitization?" into a named predicate (a small map or method) the handler calls, instead
of an inline `==`. A fuller fix (a per-level policy descriptor: requires-sanitize,
requires-workspace) crosses into `foundation` where the enum lives — note it there.

---

## Domain summary

The reassuring headline: the registry is schema-driven end to end, so your "extra
orchestrator argument" fear is **already a zero-registry-file change** — the one seam you
wanted exists. The two real issues are both in `handler/support.py`: it's a 357-line
god-file mixing skills parsing, overlay re-wrapping, expert-agent assembly, *and*
orchestrator-agent assembly under a docstring that only mentions experts (R1); and it
carries three near-duplicate wrapper factories whose name/doc/closure scaffolding is
copy-pasted (R2). Split the file by concern and collapse the factories to one
`_make_wrapper(..., invoke=…)` and the only accidental coupling here is gone. The Low items
(R3-R5) are worth doing opportunistically when you next touch those files.
