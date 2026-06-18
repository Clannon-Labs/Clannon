# Orchestration — Weaknesses & Evolution

**Status:** analysis + forward plan (not canonical architecture). **Implemented so far (June 2026):**
the full efficiency set Track A — W1 control-center self-routing, W3 prompt caching, W2 deferred tool loading,
W6 background learn, W7 search fix, W8 history (cache + condense-not-delete + `recall`), W9 retry trim. W10
(model cascade) is a **conscious skip** (see §2). The remaining forward plan is the Track-B capability gate (§7).
**Canonical design lives in** [`../SYSTEM_ARCHITECTURE.md`](../SYSTEM_ARCHITECTURE.md) → Orchestrator, and
[`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md). This document does **not** redefine the
architecture; it critiques the current implementation and proposes a phased evolution.
**Scope:** `backend/core/llm`, `backend/core/orchestrator`, `backend/registry/capabilities/handler`,
`backend/experts`, `backend/tools`. The **memory layer** (`core/memory`) and the **security pipeline**
(verifier / sanitizers / filter) are separate workstreams — referenced here only as dependencies.
**Date:** June 2026.

**Two drivers** push this evolution, and they are different things:

- **Track A — Efficiency.** "So many tokens / round-trips for a small task." §1–§2, §6.
- **Track B — The V1 capability gate.** [`../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md`](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
  defines the outcomes Clannon must demonstrate before any outreach. Today the orchestration/experts/tools
  layer **cannot pass most of it** — whole capabilities are missing, not just slow. §3, §7.

The gate is the outreach-blocking priority; efficiency Track A is cheap, rides alongside, and several of
its changes (deferred tool loading, plan-then-parallel) become *mandatory* once the gate work expands the
roster. The reconciled sequence is §8.

---

## 0. TL;DR

The topology is right — a lead orchestrator over parallel domain experts is what Anthropic's own research
system converged on. But "right shape" is not "passes the bar":

- **Efficiency (Track A):** the orchestrator is *already* a tool-driving agent that self-triages — handed
  "hi", a capable model just answers; it does not boot a 20-turn fan-out. So the cost/latency multipliers are
  not "we run the full topology for every request" — they are that **every turn re-sends the full system
  prompt + tool catalog**, with unbounded history and no prompt caching, plus hydrate/learn running around
  every turn. Recover most of it WITHOUT a separate pre-classifier:

  | # | Change | Primary win | Effort |
  |---|--------|-------------|--------|
  | 1 | **Control-center self-routing** — reinforce (in the prompt) that the orchestrator answers simple turns directly; no separate router LLM hop | speed + cost | S |
  | 2 | **Prompt caching** of system prompt + tool schemas across turns/session | cost (biggest single lever) | S |
  | 3 | **Deferred tool loading** — stop sending all schemas every turn | cost + scales with roster | M |
  | 4 | **Plan-then-parallel** — one upfront plan, independent experts batched | speed + cost + quality | M–L |
  | 5 | **`memory.learn` off the critical path**; bound history; fix search double-summary | speed | S |

  > **Design note (June 2026): no separate triage router.** An earlier draft of this doc proposed a
  > rule→semantic→LLM classifier in front of the orchestrator. We rejected it. The orchestrator already
  > decides, on turn one, whether to answer directly or reach for a tool/expert, so a pre-classifier mostly
  > adds a **serial LLM hop** (the very latency we're cutting) plus its own model/prompt/fallback to maintain —
  > and it can misroute just like a cheap model can. The one thing a router claims (don't ship the big catalog
  > on simple turns) is delivered better by **prompt caching (W3)** + **deferred loading (W2)** with no extra
  > hop. Revisit a real router only at a scale where a much cheaper router model + a very large roster make the
  > hop pay for itself. W1 below is therefore a *prompt* change (make the existing self-routing explicit and
  > reliable), not a new stage.

- **Capability gate (Track B):** the V1 benchmark needs **all 6 critical + ≥1 exceptional**. The
  orchestration/experts/tools layer scores roughly **1 near-pass, 2 partial, 6 fail** (§3). The misses are
  missing *subsystems* — repository intelligence and a cross-media knowledge graph don't exist at all — plus
  missing orchestration *patterns* (deliberation, consistency checking). Closing them is §7.

**Bottom line:** the gate is the near-term priority. The build order in §8 front-loads the longest gate item
(repository intelligence), folds in the cheap efficiency wins, and treats the **memory layer as a parallel
external workstream** that several benchmarks depend on.

---

## 1. Current shape and where the tokens go

One turn is **three nested reactive loops**, each an independent LLM tool-loop:

```
orchestrator.run (stage, 480s ceiling)
└─ run_loop: hydrate memory  ── 1 memory round-trip BEFORE the turn
   └─ Capabilities.run_turn  ── orchestrator agent, up to ORCHESTRATOR_MAX_TURNS = 20 LLM calls
       │   every tool (~5 non-workspace) + every expert (~8) offered as native tools, RESENT each turn
       ├─ spawn web.research  ── expert agent, up to EXPERT_MAX_TURNS = 8 LLM calls
       │     └─ each turn may call search.web ── grounded_search = ANOTHER full Gemini LLM call
       ├─ spawn synthesis.writer ── expert agent, more LLM calls, re-reads full findings
       └─ final answer (deliverable_ref)
   └─ memory.learn  ── 1 MORE LLM call, ON the critical path, AFTER the answer exists
```

**Round-trip count for one "research X and write a brief" task** (conservative):

| Source | LLM calls |
|--------|-----------|
| hydrate (embed + Qdrant; may include a memory LLM pass) | 1 |
| orchestrator loop (spawn research → spawn writer → answer) | ~3 |
| research expert loop (3 search turns + 1 synthesis) | ~4 |
| `search.web` grounded calls (one per search turn) | ~3 |
| writer expert loop | ~2 |
| `memory.learn` | 1 |
| **orchestrator-layer subtotal** | **~14** |
| (+ input verifier, normalizer, output filter — outside this scope) | +3 |

≈ **14 orchestration-layer LLM round-trips for a single "small" task**, and the heavy ones re-send a large
system prompt, the full tool/expert schema set, and a growing message history *every turn*. Each call is
additionally wrapped in up to 5 retry attempts (`LLM_TRANSIENT_MAX_RETRIES = 4`) over a 3-model
`FallbackModel` chain. That is the felt cost.

Key constants (`foundation/vocab/constants.py`):
`ORCHESTRATOR_MAX_TURNS=20`, `ORCHESTRATOR_TIMEOUT_S=480`, `ORCHESTRATOR_MAX_TOKENS=8096`,
`EXPERT_MAX_TURNS=8`, `EXPERT_TIMEOUT_S=240`, `EXPERT_MAX_CONCURRENT=3`, `TOOL_TIMEOUT_S=30`,
`LLM_TRANSIENT_MAX_RETRIES=4`, `LLM_RETRY_MAX_DELAY_S=30`.

---

## 2. Efficiency weakness inventory (Track A)

Each item: evidence → impact → axis (Speed / Cost / Quality / Robustness) → severity.

### W1 — Every turn carries the full capability surface (self-routing is fine; the *payload* isn't)  ·  Cost  ·  **High**
`orchestrator.py` runs the same *scaffold* for everything: hydrate → tool-driving agent with the entire
capability surface offered → `memory.learn`. But the agent itself already self-triages — a "rephrase this" or
a one-line follow-up resolves in **one** turn (the model just answers; it does not spawn experts), while a
10-source brief uses many. So the waste is **not** "a 20-turn agent boots for every request." The waste is
that **every one of those turns re-sends the full system prompt + all ~13 capability schemas** (W2/W3), and
that hydrate/learn run around even the one-turn turns (W6, mostly fixed). **Fix the payload, not the routing:**
reinforce control-center self-routing in the prompt (cheap, §6.1), then cache the prefix (W3) and defer the
long-tail catalog (W2). A separate pre-classifier is explicitly **not** the fix (see §0 design note + §6.1).

### W2 — Tool/expert schemas resent on every turn  ·  Cost  ·  **High**  ·  **DONE (June 2026)**
`build_orchestrator_tools` (`handler/support.py`) used to hand the agent **every** tool + expert as a native
tool, so the same multi-thousand-token catalog was re-billed every turn — cost growing linearly with turns
and roster size, right as §7 grows the roster from ~9 experts to ~14+.

**Fixed:** capabilities now carry an `eager` flag (default **False**). Only the hot path (`web.research`,
`synthesis.writer`, `search.web`, plus the always-on `say`/`remember`) is offered up front; everything else
is wrapped as a deferred `Tool(defer_loading=True)` and hidden behind tool search until the model looks for
it. On Anthropic (tool search GA on Haiku 4.5+) the deferred defs stay out of context until discovered; on
providers without native search the framework's local `search_tools` fallback does the same. Net: the eager
surface (and the W3-cached prefix) stays flat as the roster grows — a new expert defaults to deferred and
costs nothing until needed. See §6.3.

### W3 — No prompt caching  ·  Cost  ·  **High**
Confirmed: no `cache_control` / cache-point plumbing anywhere in `backend/` (only vendored libs).
`build_tool_agent` (`core/llm/framework.py:85-115`) builds `ModelSettings` with no caching. The system
prompt (300–560 lines) + tool catalog are stable across all 20 turns and the session — the ideal cache
prefix — yet every turn pays full input price. ~90% input-token discount on cache hits for near-zero work.

### W4 — Reactive ReAct, no plan  ·  Speed+Cost+Quality  ·  **High**
The orchestrator decides turn-by-turn (`Capabilities.run_turn`). No upfront plan, so it discovers task
shape by trial: spawn research, *then* realize it needs the writer, *then* answer — serial turns where a
plan would say "research A,B,C in parallel, then synthesize." The product vision's **entropy →
spawn-count** idea is **not implemented**; spawn count is whatever the model emits per turn. (This is also
the substrate for the §7 deliberation pattern — build it once.)

### W5 — Fan-out depends on the model, not the design  ·  Speed  ·  **Medium**
`run_experts` already supports parallel batches (`asyncio.gather`, semaphore `EXPERT_MAX_CONCURRENT=3`,
`handler/experts.py:42-47`). But the orchestrator only sees **per-expert single-shot** tools
(`_make_orchestrator_expert_fn` runs exactly one expert, `support.py:332-334`). Two independent subtasks run
in parallel **only if** the model emits two tool calls in one turn — no batched "fan out N" affordance, no
`parallel_tool_calls`. Infrastructure exists; the design doesn't drive it.

### W6 — `memory.learn` on the critical path  ·  Speed  ·  **Medium**
`orchestrator.py:74-83` awaits `ports.memory.learn(...)` *after* the answer exists but *before* the stage
returns. The user waits on a learning call before the filter→delivery handoff. Best-effort but blocking;
belongs in a background task. (The distillation internals are the memory workstream; the **call site** is
ours.)

### W7 — `search.web` double-summarizes (lossy + extra call)  ·  Quality+Cost  ·  **Medium**  ·  **DONE**
`grounded_search` ran its own Gemini agent that summarized, then the research expert reasoned over that
already-summarized text (lossy for citations), and it built a **fresh `Agent` every call** with `sources`
always `[]`. **Fixed (§6.6):** the search agent is now built once per layer (`lru_cache`); the prompt asks for
**source-attributed, detail-preserving** findings (no pre-summarizing — the expert does the final synthesis);
and `sources` is populated by a provider-agnostic extractor that pulls URLs from the grounded text and any
URL-bearing result parts (closes the `sources=[]` TODO).

### W8 — Unbounded history re-sent every turn  ·  Cost  ·  **Medium**  ·  **DONE**
`ctx.conversation` was fed as full chat history every run and re-billed on every loop turn; the old
over-budget trim **deleted** the oldest turns.
> This needs to be carefully managed and the recent chat messages (both given by user and agent output)
> should be as is, and only summarize very old messages in the chat, summarize them, not deleting.. they might
> be important too
> Biggest flaw is agent forgetting things we talked about in the same chat, even if it forgot, it should be
> able to find and see any message (input + output) at any time in the session

**Fixed (§6.5), to that spec, in three parts:**
1. **Cost** — `anthropic_cache` is now on for the multi-turn layers (orchestrator + expert roles), so the
   growing message history is a cheap cache read across a loop's turns, not a full re-bill.
2. **Condense, never delete** — recent turns stay **verbatim**; when a session exceeds the (generous) char
   budget the oldest turns are folded into a single **recap** at the front of the history (gist preserved),
   not dropped.
3. **Recall anything, anytime** — the full untrimmed transcript rides on `ctx.session_transcript`, and a new
   always-on **`recall(query)`** tool returns the verbatim text of any earlier turn by keyword. So even a
   condensed turn is fully recoverable: the agent looks it up instead of forgetting.

### W9 — Nested retry × fallback × loop → latency blow-up  ·  Robustness  ·  **Medium**  ·  **DONE (trim)**
A single failing call used up to 5 attempts with 2+4+8+16s ≈ 30s of backoff, nested inside the expert and
orchestrator loops. **Fixed (§6.7):** `LLM_TRANSIENT_MAX_RETRIES` dropped 4 → **2** (≈6s instead of ≈30s of
single-model backoff). The other two ideas from the original plan are **already covered** and deliberately not
re-built: the whole-chain re-run is already capped hard (`LLM_FALLBACK_MAX_RETRIES = 1`, prior session), and
the whole-loop / per-expert timeouts already bound wall-time — sustained rate-limits are handled by **rotating
providers/keys in the FallbackModel chain**, which is why a single model no longer needs to back off for 30s. A
per-provider circuit-breaker would have to reach inside `FallbackModel` (which hides provider selection), so it
isn't a clean fit and the chain-cap already prevents the storm-amplification it was meant to stop.

### W10 — One orchestrator model for all complexity  ·  Cost/Quality  ·  **Low–Medium**  ·  **SKIP**
`models.yaml` pins one orchestrator model (dev: `claude-haiku-4-5`). No cascade (start cheap, escalate on
complexity).
> This is not an immediate needed fix, if it is just a small edit away, we can try doing so, but ideally
> It's not needed and shouldn't be done in my opinion

**Decision (June 2026): not doing it.** A runtime cascade needs a complexity signal to decide *when* to
escalate — exactly the pre-classifier we rejected in W1 — and it is not a small edit (a second orchestrator
model, a mid-loop switch point, and the judgment of when a turn is "hard"). The cheap, already-available
alternative covers the real need: `models.yaml` + the per-session model override let prod simply **pin a
stronger orchestrator model** (e.g. sonnet) with no cascade machinery. Revisit only if cost data later shows a
cheap model wasting most turns while a few genuinely need a bigger one.

### Non-weaknesses — keep these
- **Two-output split** (`ExpertSummary` to model, full `ExpertFindings` to `ctx`) — correct context
  hygiene; keep. It's also the seam the §7 KG/repo/deliberation work plugs into (`finding_refs`).
- **`deliverable_ref` indirection** (`loop.py:61-68`) — full report becomes the response without transiting
  the orchestrator's context. Keep.
- **Graceful degradation** (`utils/recovery.py`) — LLM-free honest partial answer. Keep; lean on it harder
  once deadlines tighten (W9).
- **Capability self-registration + guarded handler** (grants/permission/SSRF/NETWORK re-sanitize/output
  cap) — the security spine. Every new expert/tool in §7 routes through it unchanged.
- **Quota-resilience fallback chains** — keep; just stop letting them amplify latency (W9).

---

## 3. Capability gaps vs the V1 Attention Threshold (Track B)

The benchmark measures **outcomes**; the gate is **all 6 critical + ≥1 exceptional**. Verdicts below are
from the orchestration/experts/tools standpoint only — the security pipeline and frontend are scored
elsewhere, and the **memory layer is a separate workstream** (so Gap A is owned there; we own only its
orchestration-side touchpoints).

| Benchmark | Verdict | Root gap |
|---|---|---|
| CB1 Persistent Cross-Session Memory | **PARTIAL** | A — flat memory records *(memory workstream)* |
| CB2 Large Repository Understanding | **FAIL** | C — no repo intelligence exists |
| CB3 Unified Multi-Modal Representation | **FAIL** | B — no cross-media knowledge graph |
| CB4 Institutional Decision Memory | **FAIL** | A + D — no decision records, no deliberation |
| CB5 Security Validation | **PARTIAL → PASS** | E — observability/classification only |
| CB6 Multi-Agent Consistency | **PARTIAL** | D — no runtime consistency check |
| Exc1 Knowledge Evolution | **FAIL** | A — no temporal/supersession *(memory workstream)* |
| Exc2 Autonomous Project Continuity | **FAIL** | A — depends on structured state *(memory workstream)* |
| Exc3 Cross-Media Synthesis | **FAIL** | B — depends on the graph |

Five gaps. Verified greenfield: **no KG/repo/entity/graph/index module exists** anywhere under
`backend/` (`core/` is `intake, llm, memory, normalizer, orchestrator, verifier, artifacts, pipeline` —
nothing else). `writer.distill` emits only flat SEMANTIC/PROCEDURAL proposals (`core/memory/writer.py`).

### Gap A — Memory stores text, not structured reasoning  → CB1, CB4, Exc1, Exc2 · **memory workstream**
Retrieval works (4 tiers, `user_id` scoping, trust+recency, Lagrangian budget). What's missing is
*structure*: typed records (decision / TODO / assumption / preference) with **status** (open/resolved/
invalidated), **temporal validity** (superseded-by, valid-as-of), and **rich provenance** (which source).
Today the orchestrator's episodic write is a flat string `f"task: {…} | answer: {…}"` (`orchestrator.py:60`)
and `MemoryWriteProposal` is `{store, content, rationale, confidence}` (`foundation/contracts/memory.py:77`).
**Owned by the memory workstream.** Our coordination obligations are listed in §7.A.

### Gap B — Media terminates in summaries; no cross-media graph  → CB3, Exc3
The `media` expert understands a file bundle and returns an `ExpertOutput` summary; the writer turns N
findings into prose. That is exactly the explicit failure condition: *"modalities remain isolated / results
are merely summaries."* No entity extraction, no relationship/graph builder, no cross-media contradiction
detection (the `verification` expert only checks one claim-set against its own cited sources). Detailed in
§7.B. References [`../knowledge_graph/`](../knowledge_graph/).

### Gap C — No repository intelligence  → CB2
Nothing navigates a repo larger than context. Workspace tools (`file_read`, `code_run`, `python_exec`)
operate on uploaded files in a no-network sandbox, **not** a large external codebase. No code-search/grep,
no symbol/AST index, no dependency-graph tool, no repo-ingest, no navigation expert. "What breaks if X is
removed / transitive dependents of Y" is unanswerable. Detailed in §7.C. The largest single build.
References [`../repository_intelligence/`](../repository_intelligence/).

### Gap D — Parallel ≠ deliberation; no consistency check  → CB4, CB6
Experts run **parallel and independent** (`run_experts` → `asyncio.gather`); only the writer reads prior
findings by ref. No **deliberation** pattern (CB4 wants agents to discuss Option A vs B and record reasoning
+ tradeoffs + participants), and no runtime **consistency verifier** (CB6 wants parallel outputs to stay
contract-compatible — the `architecture-boundary`/`security-review` agents are *dev-time*, not runtime).
Detailed in §7.D. Shares substrate with W4/W5.

### Gap E — Security works, but it's opaque  → CB5
Prevention is strong (handler guards; verifier + filter + locked prompts; experts never write memory
directly). The miss is CB5's **"classify attack" + "explain decision"**: no structured security event in the
audit/decision log, and memory **write proposals aren't re-scanned for poisoning** before they reach the
memory layer. Detailed in §7.E. Smallest lift; flips CB5 partial → clean pass.

### How Track B interacts with Track A
- Gap D **is** W4/W5 plus a critique round — build the plan-then-parallel substrate once, use it for both.
- The §7 roster jump (KG, repo, contradiction, consistency experts/tools) makes **W2 deferred loading and
  W3 caching non-optional** — without them every new capability is re-billed on every turn.
- Repo + KG experts are deep multi-hop loops → **W9 deadlines** and **W10 model cascade** matter more, not
  less, once they exist.

---

## 4. State of the art, June 2026

What the field settled on this past year, mapped to the gaps each addresses.

**Efficiency (Track A):**
- **Orchestrator-workers sized to the query (Anthropic).** Embed complexity→effort scaling ("simple = 1
  agent / comparison = 2–4 / complex = 10+") and parallelize 3–5 subagents — "cut research time up to 90%."
  Cost caveat that justifies triage: agents ~4× chat tokens, multi-agent ~15×. → W1, W4, W5.
  ([multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system))
- **Programmatic / code-execution tool calling (Anthropic, Nov 2025).** Model writes code that orchestrates
  tools in a sandbox; results stay in-sandbox. **37%→98.7% token reduction**, ~60% faster on tool-heavy
  tasks. We already have the Docker workspace. → W2, W5; and a natural fit for the §7.C repo tools.
  ([advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use))
- **Tool Search / deferred loading (Anthropic + PydanticAI).** `defer_loading=True` + `search_tools`:
  **~72K → ~500 tokens** of tool defs, preserving the cache prefix. → W2, W3.
- **Plan-and-execute / LLMCompiler.** Plan a DAG, run independent nodes in parallel. **up to 3.7× latency,
  6.7× cost, +9% accuracy** vs ReAct. → W4, W5.
  ([LangChain plan-execute](https://www.langchain.com/blog/planning-agents),
  [LLMCompiler](https://arxiv.org/pdf/2312.04511))
- **Routing / cascades (FrugalGPT → 3-tier rule→semantic→LLM).** Most requests exit cheaply. The pattern fits
  a responder that *can't* cheaply opt out of work; our orchestrator already opts out on turn one, so we take
  the *spirit* (cheap path for simple turns) via control-center self-routing + caching rather than a separate
  classifier stage. A model **cascade** (cheap orchestrator model, escalate on complexity) is still live → W10.
  ([3-tier cascade](https://blog.meganova.ai/the-3-tier-routing-cascade-rule-based-semantic-llm/))
- **Prompt caching** — table stakes for a fixed prefix + tool catalog across a multi-turn loop. → W3.

**Capability (Track B)** — established directions; each subsystem design in §7 should run its **own focused
research pass** (don't treat these as settled here):
- **GraphRAG / entity-relationship knowledge graphs** for unifying multi-source, multi-modal evidence with
  provenance and contradiction surfacing. → Gap B.
- **Code-graph / AST-aware repo RAG + agentic code navigation** (symbol + dependency indices traversed by
  an agent rather than ingested into a prompt). → Gap C.
- **Multi-agent debate / "society of mind" / LLM-as-judge panels** for deliberated decisions with recorded
  rationale and attribution. → Gap D.

---

## 5. Target architecture

Same spine, three additions on the efficiency side (router in front, planner at the loop top, progressive
disclosure + caching underneath), and an **expanded capability surface** on the gate side. Security stages
(verifier in, filter out) are unchanged and still wrap everything.

```
request
  │
  ▼
┌──────────────────────┐  the ORCHESTRATOR itself decides, on turn one (no separate classifier):
│  ORCHESTRATOR        │   simple / conversational ─► answer directly (no experts; hydrate is parallel + cheap)
│  (control center,    │   needs a fact / compute ──► one or two utility tools, then answer
│   self-routes via    │   research-shaped ─────────► spawn experts in parallel ▼
│   its system prompt) │   decision / debate ───────► DELIBERATION mode (§7.D) ▼
└──────────────────────┘
                          │
                   PLAN (one cheap call): subtasks + which are independent → spawn count (entropy)
                          │
                   EXECUTE: batch independent experts in ONE fan-out (asyncio.gather, already there);
                            deferred tool loading; cached prefix
                          │
                   synthesize (deliverable_ref) ──► filter ──► deliver
                          │
                   memory.learn ◄── BACKGROUND, off the critical path

Capability surface after the gate (new = §7):
  experts:  web.research · synthesis.writer · media.analyst · code.engineer · data.analyst ·
            verification · documentation · summarization · notification
            + knowledge.graph(B) · repo.navigator(C) · consistency.verifier(D)   [+ a moderator role for D]
  tools:    search.web · web.fetch_url · memory.search · fs.read/write · code.run · python_exec ·
            http_request · calculator
            + kg.extract / kg.contradictions(B) · code.search / code.symbols / code.dependents / code.structure(C)
```

The orchestrator loop still runs every turn — but for a simple turn it's a single answer (the prompt makes
that the default), and carrying the catalog is made cheap by caching rather than avoided by a pre-classifier.
For complex turns we plan once and fan out instead of discovering shape turn-by-turn, and gain three new
experts + a deliberation mode to clear the gate.

---

## 6. Efficiency changes — concrete (Track A)

All SDK use stays behind `core/llm` (invariant §III.12). Snippets are design sketches (PydanticAI 1.x), not
the implementation.

### 6.1 Control-center self-routing (W1) — in the orchestrator system prompt, not a new stage
No separate classifier. The orchestrator is already a tool-driving agent that, on turn one, chooses whether to
answer directly, call a tool, or spawn experts. We make that choice *explicit and reliable* in the system
prompt: it leads with a control-center stance ("you decide whether a turn needs a tool, an expert, or just a
direct reply; most turns are simple — don't reach for tools/experts unless the task needs a capability you
lack") and keeps the existing §5.1 "can you answer with no tools?" gate. A direct answer already maps cleanly
to the conversational `message` channel (`loop._split_message_and_deliverable`), so a simple turn is one
cached call with no deliverable — nothing else to build.

What this deliberately does NOT add: a rule→semantic→LLM pre-classifier. That would put a **serial LLM hop in
front of every request** (the latency we're cutting), needs its own locked model/prompt/fallback, and can
misroute exactly as a cheap model can. The thing a router would save — not shipping the full catalog on a
simple turn — is delivered by **W3 prompt caching** (the catalog becomes a ~free cached prefix) and **W2
deferred loading** (the long tail isn't sent at all), with no extra hop. See the §0 design note.

The remaining signal a router would have carried — *complexity → spawn budget / model tier* — still has a home:
the prompt already gates spawn count on how multi-faceted the request is (§5.3), and a **model cascade** (W10)
can escalate the orchestrator model on genuinely hard turns. Neither needs a pre-classifier.

Guardrail unchanged: routing is the orchestrator's own decision among paths that **all** still pass through the
verifier (upstream, already done) and the output filter (downstream) and the guarded handler. Self-routing
never bypasses a security gate — it only decides how much work to do.

### 6.2 Prompt caching (W3) — in `model_settings_for_layer` · **DONE**
`model_settings_for_layer` sets `anthropic_cache_instructions` + `anthropic_cache_tool_definitions` for every
layer, marking the stable prefix (system prompt + tool catalog) cacheable so all the turns of a run + bursty
same-prompt requests reuse it (~1.25x write once, ~0.1x reads after). Keys are Anthropic-namespaced (other
providers in a fallback chain ignore them); deferred tools (6.3) are auto-excluded from the cached block so a
mid-run discovery doesn't invalidate it.

### 6.3 Deferred / on-demand capabilities (W2) — in `build_orchestrator_tools` · **DONE**
Implemented as tool-level deferral driven by capability metadata, not a per-request hint:
- `CapabilitySpec.eager: bool = False` — a new field the `@tool`/`@expert` decorators read off the class.
  The hot path opts in (`eager = True` on `web.research`, `synthesis.writer`, `search.web`); the default-False
  long tail (media/code/data/verification/summarization/documentation/notification experts + the situational
  utility tools) defers automatically.
- `build_orchestrator_tools` wraps each non-eager wrapper in `Tool(defer_loading=True)` (the `Tool` type is
  re-exported through the `core/llm` boundary so capability code never imports the SDK directly). The
  framework auto-injects `search_tools` whenever a deferred capability exists; on Anthropic it uses the native
  GA tool search (bm25/regex), elsewhere the local `search_tools` fallback. Both keep deferred defs out of the
  prompt until the model discovers them.
- `say`/`remember` stay eager; the orchestrator prompt (§3.5) tells the model to `search_tools` for anything
  not in front of it rather than assume it's unavailable; the loop hides the `search_tools` step from the
  decision log (internal plumbing, like memory).
- Composes with W3: deferred tools are auto-excluded from the cached tool block, so growth doesn't bloat the
  cached prefix either. **This is what keeps context flat as §7 adds experts** — a new expert costs nothing
  until needed.

### 6.4 Plan-then-parallel (W4, W5) — top of `run_loop`
One cheap planning pass → subtasks tagged independent/dependent → independent ones spawn in a single
fan-out through the existing `asyncio.gather`. Expose a **batch** `spawn_experts(requests: list)` tool.
Embed Anthropic's scaling rule; gate the spawn budget on `triage.complexity`; set `parallel_tool_calls`.

### 6.5 Off-critical-path learning + history management (W6, W8) · **DONE**
`memory.learn` is fire-and-forget off the critical path (W6, prior session). History (W8) went beyond a plain
`keep_recent` trim, per the product note: **(1)** `anthropic_cache` caches the growing history for the
multi-turn layers (`_MESSAGE_CACHE_LAYERS` in `model_settings_for_layer`); **(2)** `_build_conversation`
condenses the oldest over-budget turns into a single front recap instead of deleting them, keeping recent
turns verbatim; **(3)** the full untrimmed transcript rides on `ctx.session_transcript`, and an always-on
`recall(query)` built-in returns any earlier turn verbatim by keyword — so a condensed turn is never lost,
the agent looks it up.

### 6.6 Fix `search.web` (W7) · **DONE**
The search agent is built once per layer (`lru_cache`); the prompt asks for source-attributed, specifics-preserving
findings so the research expert does the only synthesis (no lossy double-summary); `sources` is filled by a
provider-agnostic extractor over the grounded text + any URL-bearing result parts (closes the `sources=[]` TODO).

### 6.7 Deadlines + circuit-break (W9) · **DONE (trim)**
`LLM_TRANSIENT_MAX_RETRIES` dropped 4 → 2 (interactive backoff ≈30s → ≈6s). The budget-derived per-call deadline
and a per-provider breaker are deliberately **not** built: the whole-chain re-run is already capped
(`LLM_FALLBACK_MAX_RETRIES = 1`) and the whole-loop / per-expert timeouts already bound wall-time, while a
breaker would have to reach inside `FallbackModel` (which abstracts providers away). See §2 W9.

### 6.8 Programmatic tool calling (W2, W5) — longer-term, highest ceiling
For data/code/repo experts, let the model orchestrate granted tools **in code** inside the existing Docker
workspace, returning only the distilled result. Anthropic's 37–98% pattern; folds into §7.C. Higher effort
+ security surface; stays behind `VRAKSHA_ENABLE_SANDBOX`.

---

## 7. Gate-closure plan (Track B) — spec only, no implementation

Each gap below is specified at the level [`../agents/EXPERTS_AND_TOOLS.md`](../agents/EXPERTS_AND_TOOLS.md)
uses (key, I/O, tools, permission, behavior). Every new expert/tool self-registers and routes through the
guarded handler unchanged. **No code is written until each subsystem has its own design doc + your sign-off.**

### 7.A Memory record structure — **external dependency (memory workstream)**  → CB1, CB4, Exc1, Exc2
Owned by the memory effort. What *this* layer must coordinate / provide:
1. **Stop emitting flat episodic text.** Replace `orchestrator.py:60`'s `f"task… | answer…"` with whatever
   structured proposal shape the memory workstream defines (typed record + provenance + status).
2. **Experts emit candidate records, not just prose** where relevant (e.g. the writer/verification experts
   surface decisions/assumptions as structured `MemoryWriteProposal`s for the manager to persist).
3. **A recall affordance by type + status** (e.g. `memory.search` gains a typed filter) so a "reconstruct
   project state / open TODOs / invalidated assumptions" turn can retrieve decisions, not paragraphs.
4. **Provenance carried end-to-end** so retrieved memory can be cited ("retrieved because… , sourced from…").
Tracked here only as a blocking dependency for CB1/CB4/Exc1/Exc2; the schema + store live in the memory docs.

### 7.B Cross-media knowledge graph  → CB3, Exc3
Turn media + research findings into a **shared-entity graph with provenance**, so the synthesizer can draw
conclusions no single source supports and flag contradictions.

- **Tool `kg.extract`** (READ) — in: text/finding ref (+ modality, source id); out: entities + relations +
  per-item provenance (source ref, modality, span). Deterministic-ish extraction; model-backed where needed.
- **Tool `kg.contradictions`** (READ) — in: a set of entity/claim records; out: conflicting pairs with the
  supporting sources on each side.
- **Expert `knowledge.graph` (key `knowledge.graph`)** — model_role `planner`; tools `kg.extract`,
  `kg.contradictions`, `memory.search`; in: `finding_refs` (research + media findings, by ref, like the
  writer); out: a structured graph summary + a graph artifact (the unified knowledge), plus a contradiction
  list. Behavior: build/merge entities across modalities, attach provenance, surface contradictions.
- **Graph representation** — a graph artifact (nodes/edges + provenance). **Open decision:** per-task only,
  or persisted cross-session (then it overlaps the memory workstream — coordinate). Design owned by
  [`../knowledge_graph/`](../knowledge_graph/).
- **Orchestration change:** media + research feed `knowledge.graph` (via `finding_refs`); the writer reads
  the **graph**, not raw summaries. This is what converts "merely summaries" → unified knowledge.

### 7.C Repository intelligence  → CB2  *(largest build — start first)*
Navigate repos larger than context by **traversing an index**, never ingesting the repo into a prompt.

- **Ingest/index step** — input a repository (upload archive or a connected source — **open decision**),
  parse to a **symbol index** (definitions, references) + a **dependency/import graph** + a structure/module
  map. Stored as an artifact/index keyed to the task or project. This is the heavy new infra.
- **Tools (all READ, over the index — no repo in the prompt):**
  - `code.search` — literal + semantic search over files/symbols.
  - `code.symbols` — definitions and usages of a symbol.
  - `code.dependents` — direct **and transitive** dependents of a module/symbol (answers "what breaks if X
    is removed", "what's transitively dependent on Y").
  - `code.structure` — module map + architectural boundaries.
- **Expert `repo.navigator` (key `repo.navigator`)** — model_role `code`/`planner`; tools = the four above +
  `memory.search`; in: an architecture question; out: an explanation with traced dependency chains and the
  files/symbols it walked. Behavior: multi-hop traversal (this is where W4 plan-then-parallel + W9 deadlines
  earn their keep). Pairs naturally with 6.8 (let it traverse in code).
- Design owned by [`../repository_intelligence/`](../repository_intelligence/).

### 7.D Deliberation + consistency  → CB4, CB6
Two related capabilities on the **plan-then-parallel substrate (W4/W5)** plus one critique round.

- **Deliberation orchestration mode** (the orchestrator routes a decision/debate turn here itself per its
  prompt — no separate classifier; 6.1) — spawn N positions on a
  decision, run ≥1 round where each sees the others' positions (vs today's blind `gather`), converge to a
  recorded decision. A lightweight **moderator** role manages rounds and writes the outcome — *decision +
  reasoning + tradeoffs + participants* — as a structured memory record (depends on **7.A**). Token-heavy →
  gate behind the `deliberate` route only.
- **Expert `consistency.verifier` (key `consistency.verifier`)** — model_role `planner`; in: parallel
  expert outputs (by `finding_refs`) + the shared contracts (Flow schemas, API contracts); out: a
  contract-compatibility verdict + divergence/conflict list. For CB6 (and a reusable guard for any
  multi-expert turn).

### 7.E Security observability  → CB5  *(smallest — do early)*
- **Structured security events** — when the verifier/filter/handler blocks, emit a typed entry (e.g.
  `DecisionLogEntry(kind="security", detail={type, action, evidence})`) into the audit mirror, satisfying
  CB5 "classify attack + explain decision."
- **Write-proposal sanitization** — run `MemoryWriteProposal.content` through the handler's invariant-A
  `scan_text` gate before it reaches the memory layer, closing memory-poisoning at the write boundary.
  **Open decision:** scan at proposal emission (here) vs persistence (memory workstream) — coordinate so it
  isn't done twice or zero times.

---

## 8. Reconciled roadmap (both tracks, gate-first)

Sequenced so the longest gate item starts first, the cheap efficiency wins land immediately and reduce
build-time pain, and the memory workstream runs in parallel against a known contract.

| Milestone | Work | Unblocks | Effort | Depends on |
|-----------|------|----------|--------|-----------|
| **M0 — cheap wins** | **6.2 caching ✓** · 6.5 background learn ✓ + history · 6.6 search fix · **7.E** security observability | latency/cost now; CB5 → pass | S | — |
| **M1 — make growth affordable** | **6.3 deferred loading ✓** · **6.1 control-center self-routing ✓** | W2/W1; prerequisite for a bigger roster | S–M | M0 |
| **M2 — CB2 (longest)** | **7.C** repository intelligence (ingest/index + 4 tools + `repo.navigator`) · 6.4 plan-then-parallel · 6.7 deadlines | CB2 | L | M1 |
| **M3 — CB3/Exc3** | **7.B** cross-media KG (2 tools + `knowledge.graph`; media→graph→writer rewire) | CB3, Exc3 | M–L | M1 |
| **M4 — CB4/CB6** | **7.D** deliberation mode + `consistency.verifier` (on the 6.4 substrate) | CB4, CB6 | M–L | M2/M3 substrate, **7.A** |
| **parallel** | **7.A** structured memory records | CB1, CB4, Exc1, Exc2 | — | **memory workstream** |
| **later** | 6.8 programmatic tool calling · 6.10 model cascade | deeper cost/quality | L | M2 |

**Gate math:** all 6 critical + ≥1 exceptional needs **A (memory) + B + C + D + E**, with CB5 already near.
B gives the easiest exceptional (Exc3) for free. The 90–180s demo (CB1+CB2+CB3+CB4+CB6) is exactly this
set — so M0–M4 plus the memory workstream **is** the outreach critical path.

---

## 9. Open decisions

**Efficiency (Track A):**
1. ~~Triage model — dedicated `router` role vs reuse?~~ **Resolved (June 2026): no separate router.** The
   orchestrator self-routes via its prompt; the catalog cost is handled by caching (W3) + deferred loading
   (W2). Revisit only at a scale where a much cheaper router model pays for the extra hop.
2. **Hydrate on every turn?** Hydration is prefetched in parallel with the verifier and is a cheap Qdrant
   query (no LLM), so a simple self-routed turn doesn't really pay for it on the critical path. Making it
   lazy/tool-driven would force the model to *decide* to look — which breaks "it just knows things." Keep it
   prefetched + invisible; revisit only if profiling shows the Qdrant round-trip matters.
3. **Interactive vs batch budgets** — split `ORCHESTRATOR_TIMEOUT_S`/retry counts into two profiles?

**Gate (Track B):**
4. **Repo source (7.C)** — upload-archive vs connected git source? Drives ingest design and security surface.
5. **KG persistence (7.B)** — per-task graph, or persisted cross-session? Persisted overlaps the memory
   workstream — who owns the store?
6. **Consistency verifier (7.D)** — net-new runtime expert, or promote the dev-time `architecture-boundary`
   agent into a runtime capability?
7. **Memory-poisoning scan location (7.E)** — proposal emission (here) vs persistence (memory)?
8. **Deliberation cost (7.D)** — multi-round multi-agent debate is expensive; confirm it's gated to the
   `deliberate` route only and capped by complexity.

---

## 10. Sources

- V1 bar: [`../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md`](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
  · subsystem docs: [`../knowledge_graph/`](../knowledge_graph/) · [`../repository_intelligence/`](../repository_intelligence/) · [`../memory/`](../memory/)
- [Anthropic — Multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
- [Anthropic — Advanced tool use (tool search, programmatic/code-execution, parallel)](https://www.anthropic.com/engineering/advanced-tool-use)
- [LangChain — Plan-and-Execute agents](https://www.langchain.com/blog/planning-agents)
- [LLMCompiler — Parallel function calling (arXiv 2312.04511)](https://arxiv.org/pdf/2312.04511)
- [3-Tier Routing Cascade](https://blog.meganova.ai/the-3-tier-routing-cascade-rule-based-semantic-llm/)
- [Dynamic Model Routing & Cascading survey (arXiv 2603.04445)](https://arxiv.org/pdf/2603.04445)
- PydanticAI skill references: capabilities-on-demand (`load_capability`, `defer_loading`), tools-advanced
  (`search_tools`, tool-level deferral, `timeout=`), input-and-history (`ProcessHistory` trimming).
- **Per-subsystem research still owed:** GraphRAG (Gap B), code-graph/AST repo RAG (Gap C), multi-agent
  debate (Gap D) — run a focused pass when each design doc is written.
</content>
