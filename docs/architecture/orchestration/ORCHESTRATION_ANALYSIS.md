# Orchestration — Build Plan (what's left)

**Status (June 2026).** The **Track-A efficiency set is done** (§1 — kept as a short reference). The remaining
work is the **Track-B capability gate** (§3) plus two deferred Track-A efficiency items (§2). This doc now
tracks the **forward build only**; it does not redefine the architecture.

**Canonical design:** [`../SYSTEM_ARCHITECTURE.md`](../SYSTEM_ARCHITECTURE.md) → Orchestrator,
[`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md).
**Scope:** `backend/core/llm`, `backend/core/orchestrator`, `backend/registry/capabilities/handler`,
`backend/experts`, `backend/tools`. The **memory layer** (`core/memory`) and the **security pipeline**
(verifier / sanitizers / filter) are separate workstreams, referenced here only as dependencies.

**The gate is the outreach-blocking priority.** [`../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md`](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
needs **all 6 critical + ≥1 exceptional**; today the orchestration/experts/tools layer fails most of it because
whole subsystems (repository intelligence, a cross-media graph) don't exist yet. §3 is the plan to close it.

---

## 1. Done — Track A efficiency (reference only)

All shipped and test-covered. One line each; details live in the code + commit history.

| # | What | Where |
|---|------|-------|
| W1 | **Control-center self-routing** — no triage router; the prompt makes "answer directly" the default, escalate only when a turn needs a capability it lacks | orchestrator prompts |
| W2 | **Deferred tool loading** — `eager` flag (default off); hot path eager, long tail hidden behind tool search (native on Anthropic, local `search_tools` fallback elsewhere) | `specs.py`, `handler/support.py` |
| W3 | **Prompt caching** of the stable prefix (system prompt + tool catalog); Anthropic-namespaced + provably inert on other providers | `model_settings_for_layer` |
| W6 | **`memory.learn` off the critical path** (background, gated to substantive turns) | `orchestrator.py` |
| W7 | **`search.web` fix** — agent built once per layer; source-attributed, no lossy double-summary; real `sources` extracted | `core/llm/search.py` |
| W8 | **History** — cache the growing history (multi-turn layers); **condense-not-delete** old turns into a recap; always-on **`recall(query)`** over the full untrimmed transcript | `run_driver.py`, `support.py`, `registry.py`, `context.py` |
| W9 | **Retry trim** — `LLM_TRANSIENT_MAX_RETRIES` 4→2 (≈30s→≈6s backoff); chain-cap + loop/expert timeouts already bound the rest | `constants.py` |
| W10 | **Model cascade — skipped.** Needs a complexity signal = the pre-classifier rejected in W1; prod pins a stronger orchestrator model via `models.yaml` / per-session override instead | — (decision) |

**Keep as-is (do not regress):** the two-output split (`ExpertSummary` to model, full `ExpertFindings` to ctx),
`deliverable_ref` indirection, graceful degradation (`utils/recovery.py`), capability self-registration + the
guarded handler (grants / permission / SSRF / NETWORK re-sanitize / output cap), and the quota-resilience
fallback chains. Every new capability in §3 routes through the guarded handler unchanged.

---

## 2. Not done — Track A remainder (efficiency)

### 2.1 Plan-then-parallel (W4 + W5) — top of `run_loop`
**Today:** the orchestrator is pure ReAct — it discovers task shape by trial (spawn research, *then* realize it
needs the writer, *then* answer). `run_experts` already supports parallel batches (`asyncio.gather`,
`EXPERT_MAX_CONCURRENT=3`), but the orchestrator only sees **per-expert single-shot** tools, so two independent
subtasks parallelize **only if** the model happens to emit two tool calls in one turn. The product vision's
**entropy → spawn-count** is not implemented; spawn count is whatever the model emits.

**Build:** one cheap planning pass at the loop top → subtasks tagged independent/dependent → independent ones
spawn in a single fan-out through the existing `asyncio.gather`. Expose a **batch `spawn_experts(requests:
list)`** affordance and set `parallel_tool_calls`. Embed Anthropic's complexity→effort scaling (simple = 1
agent / comparison = 2–4 / complex = 10+); gate the spawn budget on how multi-faceted the request is (the prompt
already reasons about this).

**Why it matters beyond speed:** this is the **substrate for Gap D deliberation (§3.D)** — build the plan +
batched fan-out once, reuse it for the debate pattern. (LLMCompiler-style plan-and-execute reports up to 3.7×
latency / 6.7× cost / +9% accuracy vs ReAct.)

### 2.2 Programmatic tool calling — longer-term, highest ceiling
For the data/code/repo experts, let the model orchestrate its granted tools **in code** inside the existing
Docker workspace, returning only the distilled result (Anthropic's 37→98.7% token-reduction pattern). Folds
naturally into repository intelligence (§3.C). Higher effort + security surface; stays behind
`VRAKSHA_ENABLE_SANDBOX`.

---

## 3. Not done — Track B capability gate (the main work)

The benchmark measures **outcomes**; verdicts below are from the orchestration/experts/tools standpoint only.
Verified greenfield: **no KG / repo / entity / graph / index module exists** anywhere under `backend/`.

| Benchmark | Verdict | Gap |
|---|---|---|
| CB1 Persistent Cross-Session Memory | PARTIAL | A — flat memory records *(memory workstream)* |
| CB2 Large Repository Understanding | FAIL | C — no repo intelligence |
| CB3 Unified Multi-Modal Representation | FAIL | B — no cross-media graph |
| CB4 Institutional Decision Memory | FAIL | A + D — no decision records, no deliberation |
| CB5 Security Validation | PARTIAL → PASS | E — observability/classification only |
| CB6 Multi-Agent Consistency | PARTIAL | D — no runtime consistency check |
| Exc1 Knowledge Evolution | FAIL | A — temporal/supersession *(memory workstream)* |
| Exc2 Autonomous Project Continuity | FAIL | A — structured state *(memory workstream)* |
| Exc3 Cross-Media Synthesis | FAIL | B — depends on the graph |

Each gap is specified at the level [`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md) uses
(key, I/O, tools, permission, behavior). Every new expert/tool self-registers and routes through the guarded
handler. **No code until each subsystem has its own design doc + sign-off.** With W2/W3 done, a growing roster
no longer bloats per-turn context — so the gate work can add experts freely.

### 3.0 One shared graph substrate (build this first)
The repo index (3.C), the cross-media graph (3.B), and the structured-memory graph (3.A) are **not three
separate stores** — they are **three extractors writing into one shared substrate**: **Kuzu** (embedded
property-graph DB, Cypher, on-disk, bigger-than-RAM) + **Qdrant** (vectors, already running), linked by a
`node_id ↔ vector_id` contract. Land semantically (Qdrant) → walk structurally (Kuzu). The extractors are
irreducibly different (code = tree-sitter/clang; media = scene-detect/whisper/CLIP; memory = embeddings +
entity extraction), but all write through ONE `add_nodes / add_edges / add_vectors` interface — so a code node,
a memory fact, and a video shot live in one graph and can link to each other.

**Build order:** stand up Kuzu+Qdrant + the writer interface FIRST, then add extractors as separate modules.
This resolves several "open decisions" below — the KG is a **persisted** store (not per-task), shared with
memory; the repo "index" *is* this substrate, not a bespoke one. Canonical design + tool list:
[`../knowledge_graph/CLANNON_GRAPH_STACK.md`](../knowledge_graph/CLANNON_GRAPH_STACK.md) (its README orients).
The 3.B/3.C tool+expert specs below are the **orchestration-layer interface** to this substrate (how the agent
queries it); the substrate + extractors are owned by the graph workstream.

### 3.A Memory record structure — **external dependency (memory workstream)** → CB1, CB4, Exc1, Exc2
Owned by the memory effort; what *this* layer must coordinate / provide:
1. **Stop emitting flat episodic text** — replace the `f"task… | answer…"` episodic write with the structured
   proposal shape the memory workstream defines (typed record + provenance + status).
2. **Experts emit candidate records, not just prose** where relevant (writer/verification surface
   decisions/assumptions as structured `MemoryWriteProposal`s).
3. **Recall by type + status** (a typed filter on `memory.search`) so "reconstruct project state / open TODOs /
   invalidated assumptions" retrieves decisions, not paragraphs.
4. **Provenance carried end-to-end** so retrieved memory can be cited.
5. **Read is code-only; only write uses the LLM.** Memory retrieval — hydration, `memory.search`, recall — is
   deterministic code with **no LLM in the read path** (fast, cheap, predictable; the model never has to
   "decide to look"). Only the **write** path (distilling a turn into records) uses the Memory Manager's LLM.
6. **The agent must know exactly what it holds.** Anything placed in the orchestrator's context — a memory item,
   a finding, a graph node — is either clearly **distinguished as data** (tagged with its tier / provenance /
   status, as the prompt's labelled sections already do) **or** carries enough detail that the agent can reason
   about it precisely. Never an opaque blob the model can't fully account for: if it can't deeply reason about
   something in context, that's a labelling/detail bug to fix, not the agent's fault.

### 3.B Cross-media knowledge graph → CB3, Exc3
Turn media + research findings into a **shared-entity graph with provenance**, so the synthesizer can draw
conclusions no single source supports and flag contradictions. Today media terminates in a summary and the
writer turns N findings into prose — exactly the failure condition ("modalities remain isolated / merely
summaries").
- **Tool `kg.extract`** (READ) — in: text/finding ref (+ modality, source id); out: entities + relations +
  per-item provenance (source ref, modality, span).
- **Tool `kg.contradictions`** (READ) — in: a set of entity/claim records; out: conflicting pairs with the
  supporting sources on each side.
- **Expert `knowledge.graph`** — model_role `planner`; tools `kg.extract`, `kg.contradictions`, `memory.search`;
  in: `finding_refs` (research + media); out: a structured graph summary + a contradiction list (both written
  into the §3.0 substrate, so they persist and link to memory).
- **Orchestration change:** media + research feed `knowledge.graph`; the writer reads the **graph**, not raw
  summaries. Store = the §3.0 shared substrate (the media + memory extractors write it). Design:
  [`../knowledge_graph/CLANNON_GRAPH_STACK.md`](../knowledge_graph/CLANNON_GRAPH_STACK.md).

### 3.C Repository intelligence → CB2 *(largest build — start first)*
Navigate repos larger than context by **traversing the §3.0 substrate**, never ingesting the repo into a prompt.
Today nothing does this (workspace tools operate on uploaded files in a sandbox, not a large external codebase).
- **Code extractor** (the §3.0 substrate's first extractor) — input a repo (upload archive or connected source —
  **open decision**) and write a symbol graph + dependency/import graph + structure map into Kuzu, with code
  chunks embedded into Qdrant. **Build the primitive tier first:** tree-sitter (fast, fuzzy, every language) +
  `ripgrep` fallback is enough to ship CB2 on normal repos. The precise tier (scip-clang batch index + clangd
  interactive, kernel-scale) is **additive** — it writes the same store through the same writer.
- **Pluggable, stable entry point:** the extractor (a tool, or a sub-agent if it needs to reason) and the four
  query tools below keep a FIXED signature; all the future power (precise indexing, very large codebases,
  semantic hops) is added *inside* them, never by changing how `repo.navigator` or the orchestrator calls them.
  Grow the capability without ever touching the entry point.
- **Tools (all READ, over the substrate):** `code.search` (literal + semantic), `code.symbols` (defs + usages),
  `code.dependents` (direct **and transitive** — "what breaks if X is removed"), `code.structure` (module map +
  boundaries).
- **Expert `repo.navigator`** — model_role `code`/`planner`; tools = the four above + `memory.search`; in: an
  architecture question; out: an explanation with traced dependency chains and the files/symbols it walked.
  Multi-hop traversal (where §2.1 plan-then-parallel earns its keep; pairs with §2.2). Design:
  [`../repository_intelligence/`](../repository_intelligence/) +
  [`../knowledge_graph/CLANNON_GRAPH_STACK.md`](../knowledge_graph/CLANNON_GRAPH_STACK.md).

### 3.D Decision deliberation + consistency → CB4, CB6
Two capabilities on the **§2.1 plan-then-parallel substrate** plus one critique round. Today experts run
parallel + blind (`asyncio.gather`); only the writer reads prior findings.

**The orchestrator stays the sole controller — experts never debate to "win" and self-assign work.**
Deliberation is a *decision-making* pattern, not a free-for-all. When the controller faces a real choice
(option A vs B), it **delegates scoped position tasks** it assigns ("make the case for A", "make the case for
B", "stress-test A"), collects the structured positions, and the **controller (or a moderator role it owns and
directs)** weighs them and **records the decision** — *decision + reasoning + tradeoffs + participants* — as a
structured memory record (depends on **3.A**). All downstream work is then delegated by the controller, exactly
as on any other turn. Experts argue a position **on assignment**; they never pick their own tasks. Token-heavy →
gate to the deliberate route only.

- **Expert `consistency.verifier`** — model_role `planner`; in: parallel expert outputs (by `finding_refs`) +
  the shared contracts (Flow schemas, API contracts); out: a contract-compatibility verdict + conflict list.
  For CB6, and a reusable guard for any multi-expert turn. It is a **checker the controller calls**, not a
  participant that picks up work.

### 3.E Security observability → CB5 *(smallest — quick win)*
- **Structured security events** — when verifier/filter/handler blocks, emit a typed
  `DecisionLogEntry(kind="security", detail={type, action, evidence})` into the audit mirror (CB5 "classify
  attack + explain decision").
- **Write-proposal sanitization** — run `MemoryWriteProposal.content` through the handler's invariant-A
  `scan_text` **at propose/write time** (synchronously, before it reaches memory) so poisoning is blocked at the
  write boundary. **Resolved:** scan when the proposal is emitted, but put it behind a thin seam (a single
  `scan_proposals(...)` choke point) so it can be lifted to a **background job** later without touching the call
  sites.
---

## 4. Roadmap (remaining)

M0 + M1 (the efficiency set) are **done** — see §1. What's left, gate-first:

| Milestone | Work | Unblocks | Effort |
|-----------|------|----------|--------|
| **M2.0 — graph substrate (prereq for M2 + M3)** | **3.0** Kuzu + Qdrant store · `node↔vector` contract · the shared `add_nodes/edges/vectors` writer | the foundation for CB2 + CB3 | M |
| **M2 — CB2 (longest)** | **3.C** code extractor (primitive tree-sitter+rg tier first) + 4 query tools + `repo.navigator` · **2.1** plan-then-parallel | CB2 | L |
| **M3 — CB3 / Exc3** | **3.B** media + memory extractors + `kg.extract`/`kg.contradictions` + `knowledge.graph`; writer reads the graph | CB3, Exc3 | M–L |
| **M4 — CB4 / CB6** | **3.D** controller-led deliberation + `consistency.verifier` (on the 2.1 substrate) | CB4, CB6 | M–L |
| **quick win** | **3.E** security observability | CB5 → pass | S |
| **parallel** | **3.A** structured memory records (the memory extractor on the 3.0 substrate) | CB1, CB4, Exc1, Exc2 | memory workstream |
| **later** | **2.2** programmatic tool calling | deeper cost/quality | L |

**Gate math:** all 6 critical + ≥1 exceptional needs **A (memory) + B + C + D + E**, with CB5 already near. B
gives the easiest exceptional (Exc3) for free. The 90–180s demo (CB1+CB2+CB3+CB4+CB6) **is** this set — so M2–M4
plus the memory workstream is the outreach critical path.

---

## 5. Open decisions (gate)

1. **Repo source (3.C)** — upload-archive vs connected git source? Drives ingest design + security surface.
2. **Consistency verifier (3.D)** — net-new runtime expert, or promote the dev-time `architecture-boundary`
   agent into a runtime capability?
3. **Deliberation cost (3.D)** — confirm it's gated to the deliberate route only and capped by complexity (the
   controller-stays-in-charge model is settled, §3.D).

*(Resolved: no separate triage router — W1; hydration prefetched + invisible; the KG is one **persisted**
substrate shared with memory, not a per-task graph — §3.0; memory-poisoning scan runs at **propose/write time**
behind a movable seam — §3.E.)*

---

## 6. State of the art + sources (for the remaining build)

Established directions; each subsystem should run its **own focused research pass** when its design doc is
written (don't treat these as settled):
- **GraphRAG / entity-relationship knowledge graphs** for unifying multi-source, multi-modal evidence with
  provenance + contradiction surfacing → 3.B.
- **Code-graph / AST-aware repo RAG + agentic code navigation** (symbol + dependency indices traversed by an
  agent, not ingested into a prompt) → 3.C.
- **Multi-agent debate / "society of mind" / LLM-as-judge panels** for deliberated decisions with recorded
  rationale + attribution → 3.D.
- **Plan-and-execute / LLMCompiler** (plan a DAG, run independent nodes in parallel) → 2.1.
- **Programmatic / code-execution tool calling** (Anthropic, Nov 2025; 37→98.7% token reduction) → 2.2, 3.C.

**Links:** V1 bar [`../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md`](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
· subsystem docs [`../knowledge_graph/`](../knowledge_graph/) · [`../repository_intelligence/`](../repository_intelligence/) · [`../memory/`](../memory/)
· [Anthropic multi-agent research](https://www.anthropic.com/engineering/built-multi-agent-research-system)
· [Anthropic advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
· [LangChain plan-execute](https://www.langchain.com/blog/planning-agents)
· [LLMCompiler](https://arxiv.org/pdf/2312.04511)
</content>
