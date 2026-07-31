# Clannon / Vraksha — Authoritative Architecture

> **Purpose:** The single authoritative architecture for Clannon (product) /
> Vraksha (engine). It describes the full target — a premium **Mission Operating
> Layer for intelligence systems** — and tags every component with its real
> build state, so a reader sees the whole ambition *and* knows exactly what runs
> today.
> **Authority:** This document is the top of the architecture ladder. It supersedes
> the two archived surface docs (`pendings/_archived/`) and, where they disagree on
> build state, the detailed subsystem docs under `architecture/`. It yields only to
> the Vision tier (`vision/INVARIANTS.md`, `vision/ATTENTION_THRESHOLD.md`,
> `vision/GOALS.md`).
> **Rule of this document:** where the code and a doc disagreed, **the code won**.
> Every `[BUILT]` / `[PARTIAL]` claim carries a `file:line` citation. Nothing
> `[PROPOSED]` is described as if it runs.
> **Related:** `00_START_HERE.md` · `glossary/TERMS.md` · `decisions/` ·
> `architecture/SYSTEM_ARCHITECTURE.md` (retained as detailed subsystem canon).

Names: **Clannon** = the product/brand the user sees. **Vraksha** = the backend
engine (`backend/`). **Flow** = the structured transport every stage and agent
communicates through. Clannon and Vraksha are the same system from two angles.

---

## 1. Vision & Final Definition

Clannon is a **secure, memory-native Mission Operating Layer**: the user hands over a
whole job — research, writing, coding, data analysis, media understanding,
verification, and delivery — and Clannon coordinates models, experts, tools, and
durable organizational knowledge to carry it to a *verified* finish, across sessions,
without the user managing tooling, model config, or context.

The thesis: **intelligence is becoming abundant; coordination, context, and
organizational memory are the bottleneck.** Models are interchangeable workers; the
moat is the accumulated, connected understanding of a user's projects, decisions, and
work — and the ability to drive a goal to completion over time, not just answer a
turn.

Two layers make this real:

1. **The Execution Substrate** — the built, secure pipeline that turns one verified
   request into a quality-filtered result. This is fully built today and is the
   ground every higher capability stands on.
2. **The Mission Layer** — persistent, resumable missions that own goals across
   sessions, advance autonomously within safety boundaries, and remember through a
   connected knowledge web. This is the durability core, and it is largely
   `[PROPOSED]`: designed here, built incrementally on top of the substrate.

**Final definition.** Clannon is a mission-driven, memory-native operating layer that
coordinates models, experts, tools, and a connected knowledge graph to accomplish
complex goals continuously and verifiably over time — where the user need not know
which model or worker did the work, only that the mission was genuinely completed.

---

## 2. Build-State Legend

Every component, subsystem, and box in this document carries exactly one tag. This is
non-negotiable and the reason the document can be both ambitious and honest.

| Tag | Meaning |
|---|---|
| **`[BUILT]`** | Runs in code today. Carries a `file:line` citation you can open. |
| **`[PARTIAL]`** | Partly built. The tag states exactly what exists vs. what is missing, with a citation for the built part. |
| **`[PROPOSED]`** | Designed, not built. No code path exists yet. Never described in the present tense as if it runs. |

A reader must never have to guess. If a capability is not tagged `[BUILT]` with a
citation, assume it does not run yet.

---

## 3. System Overview

```text
                                USER  /  CONNECTED PLATFORM
                                          │
  ┌───────────────────────────────────────────────────────────────────────────┐
  │  MISSION LAYER                                                              │
  │   Mission Engine            [PROPOSED]   persistent resumable goal state    │
  │   Scheduler / Waker         [PROPOSED]   advances missions headless         │
  │   Autonomy + safety gates   [PROPOSED]   budget stop · irreversible-action  │
  │                                          approval                           │
  │   Decision-log audit mirror [PROPOSED]   durable record of unattended work  │
  └───────────────────────────────────────────────────────────────────────────┘
                                          │  operates (no separate service)
  ┌───────────────────────────────────────────────────────────────────────────┐
  │  EXECUTION SUBSTRATE  (one verified request → quality-filtered result)      │
  │                                                                            │
  │  intake [BUILT] → sanitize [BUILT] → normalize [BUILT] → verify [BUILT]     │
  │        → Manager-prepared context [BUILT]                                   │
  │        → ORCHESTRATOR [BUILT]  (streams decision log live [BUILT])          │
  │             ├─ experts ×9 [BUILT]   ├─ tools ×8 [BUILT]                     │
  │             └─ entropy routing as advisory signal [PROPOSED]               │
  │        → output filter [BUILT, bounded revision] → delivery [BUILT]         │
  │        → Manager curation [BUILT; post-delivery, async]                     │
  │                                                                            │
  │  Flow is the only transport between every box above.            [BUILT]     │
  └───────────────────────────────────────────────────────────────────────────┘
            │                         │                          │
  ┌──────────────────┐   ┌──────────────────────┐   ┌───────────────────────────┐
  │ KNOWLEDGE WEB    │   │ VECTOR LAYER         │   │ STATE / STORAGE           │
  │ Kuzu graph       │   │ Qdrant 4 tiers       │   │ SQLite (today) [BUILT]     │
  │   [PROPOSED]     │   │   [BUILT]            │   │ Postgres/Supabase [PROPOSED]│
  │ asserted/inferred│   │ fastembed nomic 768d │   │ Redis hot/budget [PROPOSED] │
  │ edges [PROPOSED] │   │   [BUILT]            │   │ Stripe billing  [PROPOSED]  │
  │ GraphPort        │   │ entry by similarity →│   │ R2 wiki files   [PROPOSED]  │
  │   [PROPOSED]     │   │ walk the web         │   │                            │
  └──────────────────┘   └──────────────────────┘   └───────────────────────────┘
```

Pipeline order and the Flow-only transport are real: `backend/core/pipeline.py`
(`drive()` chains each stage via `flow.then(stage.run)`), transport contract in
`backend/foundation/transport/flow.py` (`load/next/block/warn/fail`).

---

## 4. The Execution Substrate (the built pipeline)

The substrate is fully built end to end. Each stage is a Flow-in / Flow-out function;
nothing but Flow crosses a stage boundary.

| Stage | State | Citation & what it does |
|---|---|---|
| **Intake** | `[BUILT]` | `backend/core/intake/intake.py:94-135` — rate-limit, size cap (`MAX_INPUT_SIZE_BYTES`), libmagic MIME/modality detection (`:64-91`); a `str` is always literal text, never a path (`:73-74`). No LLM. |
| **Sanitize** | `[BUILT]`, fail-closed | `backend/security/sanitizers/runner.py:70-168`; ClamAV+YARA pre-gate `pre_sanitization.py:28-29,230-256`; all five modality workers real (text = detect-secrets + Presidio; pdf = PyMuPDF + pikepdf; image = PIL + exiftool; audio/video = ffmpeg). ClamAV unreachable ⇒ `flow.fail` (`runner.py:124-126`), never pass-clean. |
| **Normalize** | `[BUILT]`, code-only | `backend/core/normalizer/normalizer.py` — no `pydantic_ai`/provider imports (`:15-22`); PDF text via `fitz`. Produces `NormalizedInput`; calls no LLM. |
| **Verify** | `[BUILT]`, real LLM, fail-closed | `backend/core/verifier/verifier.py:45-105`; structured `VerifierLLMResult` (`schemas.py:31-38`) via `build_agent("verifier",...)` (`agent.py:129-135`); deterministic regex is a hint only; every exception path ⇒ `flow.fail`. |
| **LLM seam** | `[BUILT]` | `backend/core/llm/framework.py` is the only `pydantic_ai` importer (`build_agent`, `build_tool_agent`, `run_structured`); model resolution in `core/llm/registry.py`. No other module touches the SDK. |
| **Orchestrator** | `[BUILT]` | Real native tool-driving loop, `backend/core/orchestrator/{orchestrator,loop}.py`; one real pydantic-ai agent per turn via `registry/capabilities/handler/capability.py:53-110`. The model is a structured *advisor*; Clannon code drives the loop, enforces permissions, streams the log. |
| **Experts (×9)** | `[BUILT]` | `backend/experts/{web_research,writer,code,data_analysis,documentation,media,notification,summarization,verification}/expert.py`; each delegates to the real agent runner `think()` (`registry/.../support.py:185-220`) with a substantive `system.md` + `skills/`. The two-output split is honored: brief `ExpertSummary` to the orchestrator, full `ExpertFindings` to the output pipeline (`handler/experts.py:82-101`). |
| **Tools (×8)** | `[BUILT]` | `backend/tools/` — `search.web`, `web.fetch_url`, `http.request` (SSRF-guarded), `fs.read`, `fs.write`, `code.run`, `code.python_exec`, `math.calculator`. No agent-facing memory tool exists. |
| **Output filter** | `[BUILT]`, bounded fail-closed | `backend/security/filter/filter.py:90-117`; locked security role `filter`; block ⇒ `flow.block(FILTER_REJECTED)`. Bounded revision loop in `core/pipeline.py:180-229` (see §7). |
| **Delivery** | `[BUILT]` | CLI/TUI: `backend/main.py:103-208` (Rich `Live` REPL) + `backend/delivery/delivery.py`. Web: `backend/api/sse.py:18-39` streams the decision log live over SSE (`GET /runs/{id}/stream`). |
| **Memory curation** | `[BUILT]` (post-delivery) | `core/memory/lifecycle.py` hands neutral accepted-turn evidence to `MemoryPort.process_turn`. Manager's own LLM selects no-op vs typed internal tools; code policy owns scope and persistence. |

**Flow** `[BUILT]` is the sole inter-stage transport (`foundation/transport/flow.py`;
ADR 0001). Stages may import shared contracts from `foundation`, but runtime payloads
move only through `Flow.load/next/block/warn/fail`. This is an Invariant (§III.11) and
is not negotiable for any new stage or capability.

---

## 5. Memory & The Knowledge Web

Memory is the moat. Today it is a strong vector memory; the target is a **connected
knowledge web** layered on the same vectors.

### 5.1 What runs today — vector memory `[BUILT]`

- **Four tiers**, one Qdrant collection each, shared across users and scoped by
  `user_id`: `vraksha_wiki / vraksha_semantic / vraksha_episodic / vraksha_procedural`
  (`backend/core/memory/store.py:28-33`). Trust order WIKI > SEMANTIC >
  EPISODIC/PROCEDURAL (`manager.py:58-63`).
- **MemoryPort** `[BUILT]` — the only door. Its four async methods are `hydrate`,
  `process_turn`, `list_entries`, and `delete_entry`. `MemoryManager` is sole
  implementer. Reasoning agents never receive the port.
- **Lagrangian (water-filling) budget** `[BUILT]` — per-tier floors + remainder
  distributed proportional to each tier's mean rank score, packed under a real
  `tiktoken cl100k_base` count (`manager.py:171-193, 39-56`).
- **Trust ordering + recency decay** `[BUILT]` — exponential decay, 30-day half-life,
  floor 0.5 (`manager.py:82-85`); final sort `(trust desc, score desc)` (`:195`).
- **Embeddings** `[BUILT]` — local **fastembed ONNX**, `nomic-ai/nomic-embed-text-v1.5`,
  768 dims (`backend/core/memory/embeddings.py:2,18-19,42-45`). This is the production
  default. **It is not Ollama and not a hosted API** — earlier docs saying "via Ollama"
  / "via API" are corrected. A **hosted-API embedding profile behind the same loader**
  for cloud scale is `[PROPOSED]` (provider-agnostic, Invariant §4 — no embedding space
  is load-bearing).
- **Tenant scoping** `[PARTIAL]` — runtime `user_id` payload filter built in one place
  (`store.py:121-125`, applied on every search/delete) and tested
  (`tests/memory_isolation.py`), with defense-in-depth re-checks on every hit
  (`store.py:149-159`). The **Semgrep build-gate** that would make an unscoped query a
  *build failure* is **`[PROPOSED]` — it does not exist today** (no semgrep config in
  repo; `.github/workflows/ci.yml` runs only pytest + frontend build). The single-door
  rule is the real guard now (`INVARIANT_OWNERSHIP.md` §V.20).
- **No graph today** — memories are flat, independent Qdrant points. There is no
  Neo4j/Kuzu/networkx and no edge structure anywhere (`[PROPOSED]`, below).

### 5.2 The Knowledge Web `[PROPOSED]`

Memory evolves from flat vectors to a **connected web**: entities, facts, decisions,
and missions as nodes, with typed edges between them.

- **Engine: Kuzu** `[PROPOSED]` — embedded property-graph DB (Cypher, on-disk, handles
  graphs far larger than RAM). This **resolves the prior three-way doc fork** (Neo4j vs
  Kuzu vs Qdrant-native) **in favor of Kuzu**. ADR 0005 and the conflicting KG/media
  notes are superseded on the engine choice (see §12). Neo4j remains only a future
  scale-up swap target (same Cypher).
- **Qdrant remains the vector layer** `[BUILT today]`. The web does not replace
  Qdrant — it indexes it. **Entry by similarity (Qdrant) → traverse the web (Kuzu).**
  Every graph node holds its Qdrant vector pointer (`node_id ↔ vector_id`), so retrieval
  lands semantically and then walks structurally.
- **The four tiers become node labels in one web** `[PROPOSED]`, not separate stores —
  wiki/semantic/episodic/procedural are labels on nodes in the shared graph, still
  `user_id`-scoped behind the same door.
- **GraphPort** `[PROPOSED]` — the graph is reached only through a port contract that
  mirrors MemoryPort discipline: nothing imports graph internals; the manager is the
  sole implementer; scoping and degradation rules are identical.
- **User authority = asserted/inferred edge typing** `[PROPOSED]`. User-authored nodes
  and edges are `asserted` and are **immutable to agents**. Agents may add only
  `inferred` nodes and edges. **Asserted always wins** on conflict. This is the graph
  expression of the existing wiki-beats-all trust rule (Invariant §I.4) and of the
  asserted-history discipline the Mission Engine depends on (§6).

### 5.3 Manager-owned curation timing `[BUILT]`

Memory lifecycle is an ordinary stage after delivery. Railway short-circuiting means
blocked/failed drafts never reach it. `core/memory/lifecycle.py` constructs a neutral
`MemoryTurn` from final delivered response, findings, decisions, trusted scope, trace,
and participants; it never selects a tier or constructs a write proposal.

`core/memory/curator.py` runs Manager's own bounded tool-driving LLM. `search_memory`
and `save_memory` capture trusted scope and remain internal. Saves are staged atomically,
then deterministic policy enforces tier allow-list, confidence, epistemic typing,
source-backed facts, transcript rejection, dedup, supersession, and provenance
(`created_at`, `saved_by`, `session_id`, `trace_id`, rationale, participants). Most
turns correctly save nothing. The archive lists real Qdrant entries, not run shadows.

---

## 6. The Mission Engine & Autonomy `[PROPOSED]`

This is the durability core — what turns a turn-taking agent into an operating layer.
**None of this runs today.** It is specified fully here and is built on top of the
substrate and the knowledge web.

### 6.1 A mission is state, not a conversation

A **mission** is a persistent, resumable **state machine**, stored as a first-class
**subgraph in the knowledge web**: a mission node + task nodes + dependency edges +
status. It is not a chat transcript and does not live or die with a session.

- **Lifecycle:** `active → blocked → active → … → proposed-complete → (verified) → done`,
  plus the safety states `budget-paused` and `awaiting-approval` (§6.3).
- **Success criteria are defined at creation** and stored on the mission node.
  Completion is a **gated, evidence-checked transition** — the mission analogue of the
  output filter: "proposed-complete" only becomes "done" when the criteria are checked
  against evidence. Done means *genuinely done*, never vibes.
- **Persistence is cross-session and indefinite.** A mission survives restarts and the
  system being off for weeks. It ends only on **user-end**, **user-complete**, or
  **verified-done** — never because a session closed.
- **Re-plan without losing history.** Tasks are appended or superseded, never silently
  destroyed. Completed tasks and user-set facts are `asserted` and immutable; the
  evolution record (what was tried, what failed, what changed) is preserved. This is
  the asserted/inferred discipline from §5.2 applied to mission structure.

### 6.2 The orchestrator operates the mission graph

There is **no separate Mission service or box**. The Mission Engine is a *structure +
lifecycle*, and the existing orchestrator `[BUILT]` operates that graph every turn:
reads mission/task/edge state, advances it, proposes the next tasks, and records
results back into the web. This keeps the architecture one reasoning loop, not two.

### 6.3 Autonomy model and safety boundaries

- **Autonomous by default, user-toggleable to reactive** with a single action. In
  autonomous mode a **Scheduler/Waker** `[PROPOSED]` (grown out of the background-jobs
  layer, §9/§11) wakes eligible missions and advances them **headless, with no user
  present**.
- **Safety boundaries are non-negotiable:**
  - **Budget is a hard safety stop, not just billing.** Each mission carries a token
    ceiling. On exhaustion the mission **self-pauses** (`active → budget-paused`) and
    surfaces to the user — it never silently drains spend. This re-frames the
    ADR-0004 budget layer as a *safety boundary*: the same Redis-atomic enforcement
    serves both billing and autonomy containment.
  - **Irreversible actions are gated.** Missions run autonomously on **reversible** work
    (research, draft, plan, write-to-own-graph). On **irreversible / high-stakes**
    actions (send email, spend money, publish, call an external write API) the mission
    **pauses** (`active → awaiting-approval`) and waits for the user. This is
    least-privilege extended **across time**, not just across components.

The trust story for autonomy depends on the **decision-log audit mirror** (§8): a user
must be able to ask "what did the agent do unattended last Tuesday" and get a durable,
inspectable answer.

---

## 7. Orchestration & Expert Routing

### 7.1 Control loop `[BUILT]`

The orchestrator is a Clannon-owned native tool-driving loop; the model returns one
structured decision per turn and Clannon code executes it
(`backend/core/orchestrator/{orchestrator,loop}.py`). Experts and tools are offered as
native tools through guarded handlers (`registry/capabilities/handler/support.py`,
`tools.py`, `experts.py`).

**Bounds** `[BUILT]` (`backend/foundation/vocab/constants.py`):
`ORCHESTRATOR_MAX_TURNS = 20` (`:130`), `ORCHESTRATOR_TIMEOUT_S = 480.0` (`:126`),
`ORCHESTRATOR_MAX_TOKENS = 8096` (`:129`), `ORCHESTRATOR_MAX_RETRIES = 2` (`:132`).
On timeout/exception the loop returns an **LLM-free degraded answer** assembled from
partial `ctx.expert_findings` (`orchestrator.py:83-86`, `utils/recovery.py:80-100`) —
never a blank failure. The turn cap forces a single final answer
(`capability.py:111-122`).

### 7.2 Expert routing = entropy-as-advisory-signal `[PROPOSED]`

**Current reality** `[BUILT]`: spawn count is whatever the model emits. There is no
entropy router in code (no `entropy_router.py`; grep for entropy/shannon/centroid in
app code returns nothing). `architecture/orchestration/ORCHESTRATION_ANALYSIS.md:48`
is the honest statement: *"entropy → spawn-count is not implemented."* **Every other
doc that presents entropy routing as built is corrected (§12).**

**Target** `[PROPOSED]`: embed the query, compute similarity to expert domain centroids,
and **surface that distribution to the orchestrator as structured evidence** (e.g.
`spawnReason: { entropy, centroidSpread }`). The orchestrator (the LLM) makes the actual
spawn/route decision, **informed by the math but not ruled by it**. Math narrows and
informs; the reasoner decides. This deliberately avoids both brittle math-threshold
misfires and ungrounded over-spawning. It is an advisory signal, never an automatic
gate.

### 7.3 Expert communication contract `[BUILT]`

Experts return a brief `ExpertSummary` to the orchestrator (keeps its context lean) and
buffer full `ExpertFindings` to the output pipeline (`handler/experts.py:82-101`). The
orchestrator never receives raw expert output. Hard constraint.

> **Memory access — RESOLVED → Manager-only.** `core/memory/prefetch.py`
> hydrates once before reasoning and passes only preselected Relevant User Context
> as inert data. Orchestrator, batches, experts, and ordinary tools hold no
> `MemoryPort`, `memory.*` capability, tier control, or write proposal surface.
> Non-NETWORK experts may receive a snapshot of prepared context; NETWORK experts
> receive none. No mid-task recall broker exists.
>
> After accepted delivery, `core/memory/lifecycle.py` hands neutral `MemoryTurn`
> evidence to Manager. Only Manager's own curator sees its scope-captured internal
> search/save tools. Locked by `tests/orchestrator_memory_broker.py`,
> `tests/expert_hydration.py`, `tests/memory_curator.py`, and
> `tests/memory_write_timing.py`.

---

## 8. Security Model

Security is layered, explicit, and least-privilege — across components **and across
time** (the autonomy gates of §6.3).

- **Input gates `[BUILT]`:** intake rejects malformed/oversized/unsupported; sanitizers
  clean and hard-block HIGH/CRITICAL in parallel modality workers; normalizer is
  code-only; the verifier LLM is the sole input content blocker (deterministic checks
  are hints). Failures block; infra faults fail closed. (§4 citations.)
- **Output gate `[BUILT]`, bounded:** the output filter is the sole output content
  gate. On block it returns a structured reason and the driver runs a **bounded**
  revision loop — `FILTER_MAX_REVISIONS = 2` (`constants.py:173`), feedback fed back via
  `ctx.filter_feedback`, re-running **only `run_loop`** (not the whole orchestrator
  stage). After the bound it stays blocked (fail-closed,
  `core/pipeline.py:180-229, 254-257`). **There is no "escalate to a different expert"
  path** — earlier docs claiming that are corrected (§12).
- **Locked security roles `[BUILT]`:** verifier and output filter are server-locked and
  not user-configurable (`api/app.py` rejects model overrides for locked roles;
  `api/run_driver.py` drops them). The **verifier and filter both run
  `anthropic:claude-haiku-4-5`** by default (`models.yaml:5-14,21-24,29-32`) — **not
  Gemini.** Gemini is the default only for the grounded `search` role and
  `media_expert` (`models.yaml:13-14`); the grounded-search call is what satisfies the
  XPRIZE Gemini requirement (one Gemini call + one Google product). Cross-provider
  fallback chains mean no single provider quota can fail a run (Invariant §VI.24,
  tested `tests/llm_retry.py`).
- **Identity `[BUILT/PARTIAL]`:** `user_id` is set once at the authenticated entry and
  travels in Flow context; it is never re-derived from content or model output
  (Invariant §IV.18). Postgres RLS via `SET LOCAL` is `[PROPOSED]` (no Postgres yet,
  §9).
- **Sandboxing `[PARTIAL]` — the open security weak point.** Two execution paths exist,
  **both off by default**:
  - `code.run` → **Docker** (`registry/capabilities/handler/sandbox.py:127-156`):
    `--network none`, memory/CPU/PID caps, read-only FS + writable `/workspace`,
    non-root. Plain Docker namespacing, **not gVisor/microVM**. Gated behind
    `VRAKSHA_ENABLE_SANDBOX` (`:96-99`).
  - `code.python_exec` → **in-process RestrictedPython** (`backend/tools/python_exec.py:107-133`),
    runs in the main process, self-documented as "NOT a strong sandbox" (`:5-13`). Gated
    behind `VRAKSHA_ENABLE_PYTHON_EXEC`.
  - **Target `[PROPOSED]`:** out-of-process isolation (**gVisor or microVM**) for
    `code.run`. The in-process `python_exec` is a security weak point and is specified
    here as **deprecated / to be removed**, never default-on. **Premium-OS invariant:
    no untrusted code ever executes in the main process.**
- **Untrusted fetched content `[PARTIAL]`:** content experts fetch mid-run (web pages,
  tool output) is untrusted and must re-enter sanitization/verification before
  influencing reasoning or memory (Invariant §IV.17; routing built, re-entry coverage
  flagged partial in `INVARIANT_OWNERSHIP.md`).
- **Decision-log audit mirror `[PROPOSED]`:** the live decision log is streamed
  unbuffered/unfiltered to the user `[BUILT]` (`core/orchestrator/utils/decision_log.py`
  appends to in-memory `ctx.decision_log`; delivered over SSE). It is **stream-only and
  not persisted today.** The target adds a **durable audit mirror** persisting each
  mission's decision log for after-the-fact inspection — core to the autonomy trust
  story (§6.3). The final *report* still buffers through the output filter; the log
  stream stays direct.

---

## 9. Storage & State Ownership

### 9.1 What runs today `[BUILT]`

- **SQLite** is the durable relational store for all app state — users, sessions, wiki,
  projects, runs, model prefs (`backend/api/auth.py:27-96`, `api/config.py:33`,
  `api/run_store.py:215-234`). This is the current stand-in for the production DB.
- **Qdrant** is the vector store for the four memory tiers (`core/memory/store.py`).
- **In-memory dicts** back rate-limiting and live-run state
  (`core/intake/rate_limiter.py:30-55`, `api/run_store.py:64`). Conversation continuity
  is **replay-based**: prior turns are read from SQLite + the in-memory run store and
  rebuilt as chat history each turn (`api/run_driver.py:130-156`) — not Redis hot state,
  not persisted pydantic-ai `message_history`.

### 9.2 Target ownership split `[PROPOSED]`

| Store | Owns | State |
|---|---|---|
| **Postgres / Supabase** | Billing, identity, durable truth, audit; RLS via `SET LOCAL` | `[PROPOSED]` (SQLite today) |
| **Redis** (Upstash) | Hot/ephemeral: sessions, rate-limit, **token budgets (atomic, ADR 0004)**, job status, mission scheduling cursors | `[PROPOSED]` (in-memory today) |
| **Kuzu** | The durable connected knowledge web (§5.2) | `[PROPOSED]` |
| **Qdrant** | Vectors, 4 tiers, `user_id`-scoped | `[BUILT]` |
| **Cloudflare R2** | Wiki `.md` files | `[PROPOSED]` (local/SQLite today) |
| **Stripe** | Subscription billing, `invoice.paid` budget resets | `[PROPOSED]` — `/billing/*` currently returns `501` (`api/app.py:599-606`) |

ADR 0004 (Redis-atomic budgets, Postgres truth) is **accepted but unbuilt**; in this
architecture the Redis budget layer is also an autonomy safety boundary (§6.3).

---

## 10. Quality & Speed Models

**Quality `[BUILT]` mechanisms** (ratified as-built): structured outputs with schema
validation at each stage; deterministic pre-checks before LLM calls; the output filter
as the sole final content gate with bounded revision; focused specialist experts over
one oversized prompt; trust + provenance ordering in memory; contract/safety tests
(`backend/tests/`). **Mission-level quality `[PROPOSED]`:** the gated, evidence-checked
completion transition (§6.1).

**Speed `[BUILT]` mechanisms:** deterministic gates before expensive LLM calls; small
fast verifier/filter models (`claude-haiku-4-5`); parallel modality workers in
sanitization; parallel experts (`EXPERT_MAX_CONCURRENT = 3`, `constants.py:157`);
Lagrangian-budgeted compact hydration instead of transcript replay; provider/model
routing via `models.yaml`. **Speed `[PROPOSED]`:** entry-by-similarity-then-walk graph
retrieval (§5.2); Redis hot session/context cache; background scheduler for long
missions. **Entropy-advisory routing is `[PROPOSED]`** and must not be listed as a
shipped speed mechanism.

---

## 11. Roadmap & Phasing

Each item is future work, not built. Tied to ADRs where they exist.

**Phase A — Memory-write correctness.** ✅ **Done, strengthened 2026-07-30.**
Post-delivery Manager curation replaces automatic transcript-like episodic writes;
blocked drafts never seed memory and reasoning agents cannot manage tiers.

**Phase B — Production storage & tenancy.**
- SQLite → Postgres/Supabase; add Redis (sessions, rate-limit, **atomic token budgets**
  per ADR 0004, job status). Stripe billing (today `501`).
- Multi-tenancy hardening: the **Semgrep unscoped-query build-gate** (absent today —
  stop implying it exists), Postgres **RLS via `SET LOCAL`**, and **project-scoping of
  the learned memory tiers** (today the learned tiers are account-wide; only wiki is
  project-scoped — see `proposals/archive/to-frontend/2026-06-18_orchestration-efficiency-pass.md`).
- Background-job **queue + job-status store** (today: bare `asyncio` tasks, run-id only).

**Phase C — Knowledge web.** Stand up Kuzu next to Qdrant behind a **GraphPort**; define
`node_id ↔ vector_id`; migrate the four tiers to node labels; implement asserted/inferred
edge typing (§5.2). Supersedes ADR 0005's open graph-DB question (→ Kuzu).

**Phase D — Mission Engine & autonomy.** Mission/task subgraph + lifecycle; gated
completion; Scheduler/Waker for headless advancement; the budget-stop and
irreversible-action-approval safety gates; the **decision-log audit mirror** (§6, §8).

**Phase E — Silent continuity.** Context-pressure rollover / compaction store (today
replay-based; no compaction store).

**Cross-cutting open decisions to make before/within these phases** (flagged, not
silently settled here): (1) **resolved → Manager-only, `[BUILT]` 2026-07-30**
(§7.3); (2) whether a second entity-embedding space is added
alongside nomic-768 (§5.1); (3) fail-open vs. fail-closed per background job type.

---

## 12. Superseded Docs & ADRs

**Archived (replaced by this document):**
- `pendings/_archived/VRAKSHA_FINAL_SYSTEM_ARCHITECTURE.md` — was the pipeline-only
  surface doc. Its accurate content is folded into §4–§10 here.
- `pendings/_archived/CLANNON_OPERATING_LAYER.md` — was the Mission-OS vision doc. Its
  framing is adopted as the spine here, with every component now build-state tagged
  (Mission Engine, dynamic teams, worker registry were untagged aspiration there;
  here they are `[PROPOSED]`).

**ADRs:**
- **ADR 0005 (cross-media knowledge graph)** — graph **engine question resolved → Kuzu**
  by this document (§5.2). The "graph DB choice not yet ratified" and the "e.g. Neo4j"
  example are superseded; the rest of ADR 0005 (media-becomes-knowledge intent) stands.
- ADR 0001 (Flow-only transport), 0002 (single-Qdrant `user_id` scoping), 0003 (Clannon
  owns the verifier), 0004 (Redis-atomic budgets / Postgres truth) remain accepted;
  this document re-frames 0004's budget layer as an autonomy safety boundary (§6.3) and
  notes 0002's CI gate is still unbuilt.

**Factual corrections applied to `architecture/**` and `decisions/**`** (proven-false
statements fixed; see the changelog in `reports/backend/report_v2.md` for exact lines):
embeddings runtime ("via Ollama" → fastembed local ONNX); verifier model ("Gemini" →
`anthropic:claude-haiku-4-5`); entropy routing tagged `[PROPOSED]` everywhere it was
shown as built; MemoryPort contract corrected; the Memory Manager corrected
from "stub today" to built; the output-filter "escalate to a different expert" claim
removed (bounded revision only); and the Semgrep build-gate marked `[PROPOSED]`/absent
where it was implied to exist; the Neo4j-vs-Kuzu-vs-Qdrant-native graph fork resolved to
Kuzu with superseding notes.

---

*This document is the authoritative architecture. The ambition is the spine; the
build-state tags are the honesty. If a component here is not tagged `[BUILT]` with a
citation, it does not run yet.*
