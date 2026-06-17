# Orchestration — Extension Points ("drop-in kit")

**Status:** plug-in map. No feature implementation. **Open this file instead of scanning the codebase**
when you (or a future agent) get the code for a gate capability and need to know exactly where it goes.
**Companion to** [`ORCHESTRATION_ANALYSIS.md`](ORCHESTRATION_ANALYSIS.md) (the *what* and *why*) and
[`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md) (the base capability contract).
**Date:** June 2026.

## The point of this doc

The §9 decisions in `ORCHESTRATION_ANALYSIS.md` (repo source, KG persistence, consistency-verifier origin,
poisoning-scan location) **do not need answering yet.** Every seam below is **decision-agnostic**: each
unanswered choice becomes a detail *inside* a plugged-in implementation, never a change to the seam itself.
Stand up the seams once; after that, each capability is a drop-in.

## What's already drop-in vs what needs a one-time seam

| To add… | Seam | Status |
|---|---|---|
| an **expert** (`knowledge.graph`, `repo.navigator`, `consistency.verifier`) | Seam 1 — `@expert` self-registration | **already exists** |
| a **tool** (`kg.extract`, `code.search`, `code.symbols`, `code.dependents`, …) | Seam 2 — `@tool` self-registration | **already exists** |
| a **store/index** an expert reads (KG graph, repo index) | Seam 3 — store Port + handler injection | **one-time seam** |
| an **orchestration mode** (deliberation; triage fast-paths) | Seam 4 — mode registry | **one-time seam** |
| a **security event / write-proposal scan** hook | Seam 5 — pre-reasoning/write hooks | **one-time seam** |

So **B/C/D's experts and tools are already drop-in today** — the only net-new scaffolding is three small,
inert infra seams (3, 4, 5). Once those exist, the whole gate roster is "drop a file in, it self-registers."

---

## Seam 1 — Add an expert (already exists)

Drop a `@expert` package under `backend/experts/<name>/`; `registry.capabilities.discover()` imports it so
the decorator fires. **No wiring, no registry edit, no orchestrator edit.** Behaviour lives in a co-located
`system.md` (+ optional `skills/`), never in `expert.py`. Full contract:
[`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md).

```python
# backend/experts/knowledge_graph/expert.py     (skeleton — fill the body later)
from __future__ import annotations
from pydantic import BaseModel, Field
from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think

class KnowledgeGraphIn(BaseModel):
    prompt: str = Field(description="What to unify/relate.")
    finding_refs: list[str] = Field(default_factory=list, description="Research/media findings to ingest.")

@expert
class KnowledgeGraphExpert:
    name = "graph"; domain = "knowledge"            # key = "knowledge.graph"
    description = "Unify findings across modalities into a shared-entity graph; surface contradictions."
    input_schema = KnowledgeGraphIn
    output_schema = ExpertOutput
    skills = ("skills",)                            # co-located skills/ dir (≥1 required)
    tools = ("kg.extract", "kg.contradictions", "memory.search")   # scoped grants (Seam 2 + a store via Seam 3)
    model_role = "planner"                          # resolves through models.yaml + fallback chain
    permission = PermissionLevel.READ
    tags = ("graph", "entities", "cross-media")

    async def run(self, args: KnowledgeGraphIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, args.prompt)        # two-output split + guards handled for you
```

Same skeleton for `repo.navigator` (`model_role="code"`, `tools=("code.search","code.symbols",
"code.dependents","code.structure","memory.search")`) and `consistency.verifier`
(`tools=("memory.search",)`, reads parallel outputs via `finding_refs`).

---

## Seam 2 — Add a tool (already exists)

Drop a `@tool` file under `backend/tools/<name>.py`; `discover()` registers it. The guarded handler enforces
grants / permission / timeout / output cap, and **re-sanitizes NETWORK output (invariant A)** for you. Full
contract: [`../tools` CLAUDE.md] and [`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md).

```python
# backend/tools/kg_extract.py     (skeleton)
from __future__ import annotations
from pydantic import BaseModel, Field
from foundation import PermissionLevel
from registry import tool

class KgExtractIn(BaseModel):
    text: str
    source_ref: str = ""        # provenance: which finding/modality this came from

class KgExtractOut(BaseModel):
    entities: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)

@tool
class KgExtractTool:
    name = "extract"; domain = "kg"                 # key = "kg.extract"
    description = "Extract entities + relations (with provenance) from text."
    input_schema = KgExtractIn
    output_schema = KgExtractOut
    permission = PermissionLevel.READ               # NETWORK only if it calls out; WRITE if it persists
    tags = ("graph", "entities")
    # wants_knowledge = True                        # ← opt into a store via Seam 3 (uncomment when Seam 3 exists)

    async def run(self, args: KgExtractIn) -> KgExtractOut:
        ...                                         # fill later
```

---

## Seam 3 — A store/index an expert reads (one-time seam)

KG and repo intelligence each need somewhere to keep their graph / index. The codebase already has the
pattern: a **Port Protocol in `foundation/contracts/`** (like `MemoryPort`) + **handler injection** by a
`wants_*` flag (like `wants_memory` → `MemorySearcher`, `tools.py:95`). To make stores drop-in, stand up the
port + the injection branch **once**; after that any tool just sets the flag.

**This seam is decision-agnostic:** per-task vs cross-session (KG) and upload vs git (repo) are choices made
by the *implementation behind the port*, not by the port. Cross-session persistence is where you'd coordinate
with the memory workstream — but the seam doesn't care which you pick.

```python
# foundation/contracts/knowledge.py     (new — Protocol only, no logic)
from typing import Protocol, runtime_checkable
@runtime_checkable
class KnowledgeStorePort(Protocol):
    async def upsert(self, user_id: str, nodes: list[dict], edges: list[dict]) -> None: ...
    async def query(self, user_id: str, q: str) -> list[dict]: ...
# (RepoIndexPort mirrors this: ingest(repo) -> index_id; search/symbols/dependents/structure over it.)
```

The **one-time handler edit** (mirrors the existing `wants_memory` branch in
`registry/capabilities/handler/tools.py`):

```python
elif getattr(impl, "wants_knowledge", False):
    coro = impl.run(args, knowledge_store_for(ctx))   # inject the port, scoped to ctx.user_id
```

After that: a KG tool sets `wants_knowledge = True` and receives the store — **no further handler edits.**
Default impl can be an inert in-memory stub that raises/returns empty until the real store lands. Deep design:
[`../knowledge_graph/`](../knowledge_graph/), [`../repository_intelligence/`](../repository_intelligence/).

---

## Seam 4 — An orchestration mode (one-time seam)

Today `orchestrator.run` always calls `run_loop` (`core/orchestrator/orchestrator.py:45`). Deliberation
(7.D) and the triage fast-paths (Track A 6.1) are **new modes**. To make modes drop-in, route through a small
registry whose default is the current behaviour — a behaviour-preserving no-op refactor.

```python
# core/orchestrator/modes.py     (new)
MODES = {"orchestrate": run_loop}                  # default == today's behaviour, byte-for-byte
def register_mode(name, handler): MODES[name] = handler
async def dispatch(mode, normalized, ports, ctx):
    return await MODES.get(mode, run_loop)(normalized, ports, ctx)
```

`orchestrator.run` calls `dispatch(triage.mode, …)` instead of `run_loop(…)` directly. Adding deliberation
later = `register_mode("deliberate", run_deliberation)` in one new file — **no edit to the stage door.**
Until triage exists, `mode` is always `"orchestrate"`, so nothing changes.

---

## Seam 5 — Pre-reasoning / write hooks (one-time seam)

Two CB5 needs (7.E) are single, well-known call sites — make them named hooks so the logic plugs into one
place:

- **Security event** — a typed audit entry when the verifier/filter/handler blocks. Add one helper, e.g.
  `ctx.record_security_event(kind, action, evidence)`, and call it at each block site. CB5 "classify +
  explain" then lives in that one helper.
- **Write-proposal scan** — run `MemoryWriteProposal.content` through the handler's invariant-A `scan_text`
  gate before it leaves for the memory layer. The seam is one function the orchestrator calls on
  `ctx.memory_writes_requested` before `record_write_proposals` (`orchestrator.py:65`). Whether the *final*
  scan also happens at persistence is the memory-team's call — the emission-side hook is ours and harmless to
  add now.

---

## Per-capability plug-in checklist

Once Seams 3–5 exist, every gate capability is a file-drop:

- **7.B Cross-media KG** → Seam 2 ×2 (`kg.extract`, `kg.contradictions`) · Seam 1 ×1 (`knowledge.graph`) ·
  Seam 3 (knowledge store) · rewire: media/research feed `knowledge.graph` via `finding_refs`; the writer
  reads the graph (this rewire is prompt/skill content, not code).
- **7.C Repo intelligence** → Seam 2 ×4 (`code.search`/`code.symbols`/`code.dependents`/`code.structure`) ·
  Seam 1 ×1 (`repo.navigator`) · Seam 3 (repo index + an ingest entry point).
- **7.D Deliberation + consistency** → Seam 4 (`deliberate` mode + a moderator) · Seam 1 ×1
  (`consistency.verifier`) · built on the plan-then-parallel substrate (Track A 6.4).
- **7.E Security observability** → Seam 5 (both hooks).
- **7.A Memory records** → external (memory workstream); our side is the Seam 5 write-proposal hook + emitting
  structured proposals instead of the flat string at `orchestrator.py:60`.

## How the §9 decisions map onto the seams (so you can defer them)

| §9 decision | Lives inside | Changes the seam? |
|---|---|---|
| Repo source: upload vs git | `RepoIndexPort` impl / ingest adapter | No |
| KG persistence: per-task vs cross-session | `KnowledgeStorePort` impl | No |
| Consistency verifier: new vs promote dev agent | the `@expert` body (Seam 1) | No |
| Poisoning scan: emission vs persistence | the Seam 5 hook vs memory-side | No (emission hook is additive) |

Each is a swap behind a stable seam — pick when you implement, not now.

## One-time seams: status

Seams 3, 4, 5 are **specified, not built.** They're small, inert, and behaviour-preserving (Seam 4 defaults to
today's path; Seam 3/5 are additive branches/helpers that nothing triggers until a capability opts in).
Standing them up touches `foundation/contracts`, `core/orchestrator`, and the handler — so it wants a quick
sign-off before editing live paths. After that, the gate roster drops in file-by-file.
</content>
