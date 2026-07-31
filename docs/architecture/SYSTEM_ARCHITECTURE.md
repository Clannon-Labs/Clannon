# Clannon Final System Architecture

> **Purpose:** The canonical, system-wide architecture — major components, data
> flow, boundaries, and the principles that bind them. The single source of truth
> for how Clannon is built.
> **Scope:** The whole system end to end. Subsystem detail is delegated to the
> `architecture/<subsystem>/` folders (indexed below); this document links to
> them rather than restating them.
> **Authority level:** Tier 4 (System Architecture). Outranks subsystem docs,
> benchmarks, ADRs, and code. Yields to the Vision tier — see
> [../vision/INVARIANTS.md](../vision/INVARIANTS.md),
> [../vision/ATTENTION_THRESHOLD.md](../vision/ATTENTION_THRESHOLD.md),
> [../vision/GOALS.md](../vision/GOALS.md).
> **Related:** [../00_START_HERE.md](../00_START_HERE.md) ·
> [../glossary/TERMS.md](../glossary/TERMS.md) ·
> [../decisions/README.md](../decisions/README.md)

> **⚠️ Authority handoff (2026-06-26):** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) is now
> the single authoritative, build-state-tagged architecture and sits **above** this
> document. This file is **retained as detailed subsystem canon**, but several of its
> build-state claims were written during the Phase-1 "spine / stub" period and are now
> **stale**: experts, tools, and the Memory Manager described below as stubs/planned are
> **BUILT** today; the **entropy router remains PROPOSED — not built**. For the current
> build state of any component, defer to `../ARCHITECTURE.md`. Discrete proven-false
> statements have been corrected inline below (embeddings provider, verifier model,
> entropy routing, MemoryPort method count, Memory Manager stub claim, output-filter
> escalation, the Semgrep build-gate).

## Documentation Authority

This document sits at **Tier 4**. Conflicts resolve **upward**:

1. [Invariants](../vision/INVARIANTS.md) — never violated.
2. [Attention Threshold](../vision/ATTENTION_THRESHOLD.md) — supersedes
   architecture when elegance and demonstrability conflict.
3. [Goals](../vision/GOALS.md).
4. **System Architecture (this document).**
5. [Subsystem Architectures](#subsystem-architecture-index).
6. [Benchmarks](../benchmarks/).
7. [Decisions / ADRs](../decisions/).

If this document conflicts with a higher tier, the higher tier wins; if it
conflicts with a lower tier, this document wins and the lower tier is corrected.

## Subsystem Architecture Index

Detailed designs live in dedicated subsystem folders. Each has a README entry
point; the sections later in *this* document remain the canonical system-wide
text those subsystems elaborate.

| Subsystem | Entry point | Status | Covers |
|---|---|---|---|
| Agents | [agents/](agents/) | built (runtime) | Orchestrator, experts, tools, LLM adapter. Entropy routing is **PROPOSED — not built** (see [../ARCHITECTURE.md](../ARCHITECTURE.md) §7.2) |
| Agent Civilization | [agents/AGENT_CIVILIZATION.md](agents/AGENT_CIVILIZATION.md) | **PROPOSED — no implementation** | Pillar 4: institutional artifact protocol |
| Memory | [memory/](memory/) | built | Four tiers, Memory Manager, MemoryPort, hydration |
| Media | [media/](media/) | partial (preprocessing built; "→ knowledge" proposed) | Per-modality representations |
| Knowledge Graph | [knowledge_graph/](knowledge_graph/) | **PROPOSED — no implementation** | Pillar 2: cross-media graph / entity convergence |
| Repository Intelligence | [repository_intelligence/](repository_intelligence/) | **PROPOSED — no implementation** | Pillar 3: repo-scale reasoning without prompt-stuffing |
| Storage | [storage/](storage/) | partial (Qdrant built; Redis/budgets/sessions design-only) | Redis, Postgres, Qdrant, R2, budgets, sessions |
| Security | [security/](security/) | built | Sanitizers, verifier, output filter, threat model |
| UI / UX | [ui/](ui/) | built (mock-backed) | Product surfaces, states, design language, voice |
| Structure | [structure/](structure/) | reference | Repository + deploy layout |

**Cross-cutting architecture docs** (apply across all subsystems):

- [ARCHITECTURAL_CONVENTIONS.md](ARCHITECTURAL_CONVENTIONS.md) — how to place and
  wire code (distinct from the never-break Invariants).
- [INVARIANT_OWNERSHIP.md](INVARIANT_OWNERSHIP.md) — which invariant each module
  owns, and whether it is enforced / partial / aspirational.

> Pillar coverage at a glance: see the **Attention Threshold pillar → home** table
> in [../00_START_HERE.md](../00_START_HERE.md).

---

## Build Phase

**Production.** The Macondo submission checkpoint is complete (submitted
2026-06-12) and its build-scope gating is retired. This is a build-phase note,
**not architecture** — the current phase and roadmap live in
[../vision/GOALS.md](../vision/GOALS.md), and the full historical checkpoint
decision (its in/out-of-scope lists and build-scope rules) is preserved verbatim
in [../decisions/deprecated/0007-macondo-checkpoint-build-phase.md](../decisions/deprecated/0007-macondo-checkpoint-build-phase.md).

## Purpose

clannon is a secure, memory-native research and creation platform. It lets users
research, write documentation, build code, analyze media, and collaborate with
agents without installing local tooling, managing model configuration, or
manually preserving context between sessions.

The product promise is continuity: users should feel like they are working in
one persistent creative/research workspace. Internally, clannon may compact,
roll over, hydrate, and route sessions as needed, but users should not notice
those boundaries.

## Product Workflow

1. A user enters clannon through the default web dashboard or through a connected
   platform such as chat, email, messaging, or notification channels.
2. Raw input enters the Flow pipeline and is rate-limited, size-checked, and
   modality-detected.
3. Sanitizers inspect and clean the input before later layers touch it.
4. The normalizer converts sanitized payloads into a structured handoff.
5. The verifier validates safety, prompt-injection risk, handoff integrity, and
   model/modality routing.
6. The orchestrator builds an execution plan using current session context,
   memory, tools, experts, and user preferences. It streams a structured
   decision log to the user in real time.
7. Experts and tools perform research, documentation, coding, media analysis,
   retrieval, browser/API work, and platform interactions. Experts send brief
   structured summaries to the orchestrator and full findings to the output
   pipeline.
8. The output filter verifies final responses before the user sees them.
9. The user receives the result in the active platform, with optional dashboard
   updates, notifications, or follow-up prompts.
10. Memory write policies update the correct memory layers asynchronously
    after delivery.

## Non-Negotiable Priorities

- Security: every stage is least-privilege, auditable, and explicit about
  block/fail/warn behavior.
- Quality: research, documents, code, and UX must be reliable enough for paying
  users.
- Speed: cheap deterministic gates run before expensive LLM calls; hot context
  stays cached; slow work is routed to appropriate async/background paths.
- Continuity: session rollover and context compaction happen silently.
- Portability: users interact through the platform of their choice, while the
  website remains the default dashboard.
- Trust: user-authored knowledge and explicit user preferences outrank inferred
  memories.

## Core Architecture

```text
raw input
  -> intake
  -> sanitizers
  -> normalizer
  -> verifier
  -> orchestrator  (streams decision log to user)
  -> experts / tools / memory manager / integrations
  -> output filter
  -> delivery
  -> memory writes (async, post-delivery)
```

Flow is the only transport between stages. Stages may import shared contracts,
but runtime payloads move through `Flow.load()`, `Flow.next()`, `Flow.block()`,
`Flow.warn()`, and `Flow.fail()`. All inter-agent data transfer uses Flow's
structured schema — never free-form text between components.

Shared payload schemas live in `foundation`. Stage packages own behavior, not
transport.

## Foundation Layer

Foundation owns shared primitives:

- `Flow`
- payload handles
- context
- transport status
- pipeline stages
- origins
- threat levels
- block reasons
- model registry
- cross-stage contracts such as normalized input and verification result

Foundation must stay framework-light and provider-neutral. It should not own
business logic, sanitizer logic, memory retrieval policy, or provider SDK calls.

## Intake

Intake owns the first raw-input gate:

- request rate limiting
- raw input size limits
- MIME/modality detection
- malformed/unsupported input blocking
- recording raw input and detected modalities in context

Intake does not perform deep security analysis. It detects what the payload is
and whether it may enter the sanitizer layer.

## Sanitization

Sanitization is the security cleanup layer before normalized reasoning.

Universal pre-sanitization runs first:

- ClamAV
- YARA

Modality workers then run in parallel as needed:

- text: secrets, PII, HTML cleanup
- PDF: structure validation and dangerous feature stripping
- image: parser validation and metadata stripping
- audio: validation, metadata stripping, duration limits
- video: validation, metadata stripping, duration limits

High or critical threats block before the orchestrator can see the payload.

## Normalization

The normalizer is code-only. It does not call LLMs.

It converts sanitized payloads into a `NormalizedInput` contract:

- text becomes stable Unicode text
- PDFs become page-aware extracted text
- supported native media is preserved for the target model
- unsupported native media is marked as requiring an expert

The normalizer resolves target model capabilities through the model registry,
but does not perform final security judgment.

## Verification

The verifier is the final input gate before orchestration. It uses a small,
fast LLM with a targeted system prompt for semantic attack screening. This is
the current design — not a future addition.

It performs:

- deterministic handoff validation
- model/modality routing verification
- prompt-injection screening
- malicious-intent and semantic attack classification
- structured routing decisions

Verifier output is always structured. It never produces user-facing prose.

Possible outcomes:

- proceed directly
- proceed with warning
- route through expert
- block unsafe or unsupported input
- fail on broken pipeline/configuration state

The verifier replaced LLM Guard and Rebuff. External screening libraries are
not used. Security policy is owned by clannon, not a third-party dependency.

## LLM Framework Layer

Pydantic AI is the preferred LLM framework, but only behind a clannon-owned
adapter. The framework must not own clannon's memory, session lifecycle,
security policy, or orchestration semantics.

Expected shape:

```text
core/llm/
  registry.py       resolve model profiles into callable model configs
  clients.py        construct provider/model clients
  schemas.py        Pydantic output schemas
  verifier_agent.py structured verifier agent
  errors.py         translate provider/framework errors to foundation errors
```

Pydantic AI is used for:

- structured outputs
- typed dependencies
- tool calling
- provider abstraction
- usage limits
- async model runs

clannon owns:

- Flow
- memory routing
- session compaction
- expert selection
- security policy
- user/platform delivery

The framework SDK is confined to `core/llm` — `framework.py` is the single
build/run entry point every LLM stage uses (`build_agent` + `run_structured`), so
the framework can be swapped or audited from one place. No other module imports
the SDK.

### Model Configurability

Users may configure which model handles which pipeline layer. The system
filters available models by capability (e.g. vision, audio, long context) and
applies sensible defaults when a layer is unconfigured. Model profiles are
resolved through `models.yaml` and the model registry at runtime.

Gemini is the default provider for video, audio, image, and research tasks.

### Embedding Stack

- Model: `nomic-embed-text-v1.5` via **local fastembed ONNX** (`backend/core/memory/embeddings.py:18-45`); a hosted-API embedding profile for cloud scale is **PROPOSED**. (Corrected: not Ollama, not a hosted API today.)
- Dimensions: 768
- Vector store: Qdrant (Docker locally, Qdrant Cloud in production)

## Orchestrator

The orchestrator is the central reasoning layer. It plans and coordinates work,
but does not bypass earlier safety stages.

Responsibilities:

- interpret the verified user request
- consume pipeline-prepared relevant user context as inert data
- decide whether tools or experts are needed, and how many
- coordinate research, documentation, coding, and platform actions
- maintain task state
- stream a structured decision log to the user in real time
- prepare draft outputs for the output filter

### Decision Log Streaming

The orchestrator streams structured decision commentary to the user freely
and in real time. This is not narrative prose — it is a structured log of
what the orchestrator is doing and why (expert selection, tool invocations,
routing decisions, confidence signals). The final report is separate: it
buffers through the output filter before streaming to the user.

### Expert Spawning: Entropy-Based Routing [PROPOSED — not built]

> **Build state: PROPOSED.** Today spawn count is whatever the model emits
> ([orchestration/ORCHESTRATION_ANALYSIS.md](orchestration/ORCHESTRATION_ANALYSIS.md)
> line 48). The target is entropy-**as-advisory-signal** (math informs, the reasoner
> decides) — see [../ARCHITECTURE.md](../ARCHITECTURE.md) §7.2. The present-tense
> description below is the design target, not current behavior.

**[PROPOSED — not built.]** Today, spawn count is whatever the model emits — there
is no entropy computation in the routing path
([orchestration/ORCHESTRATION_ANALYSIS.md](orchestration/ORCHESTRATION_ANALYSIS.md)
line 48). The target below is an **advisory signal**, not an automatic gate.

The *proposed* design: embed the query, compute its similarity to each expert's
domain centroid, and surface that distribution (its Shannon entropy and spread) to
the orchestrator as **structured evidence**. The orchestrator (the reasoning model)
then makes the actual spawn/route decision, informed by the math but not ruled by it:

- Low entropy (the evidence points clearly to one domain) *suggests* a single targeted
  expert.
- High entropy (the evidence spans several domains) *suggests* spawning multiple
  experts in parallel, one per strongly activated domain.

Math informs, the reasoner decides — this is meant to avoid both brittle
math-threshold misfires and ungrounded over-spawning. None of it runs yet.

### Expert Communication Contract

Experts send two outputs for every task:

1. A brief structured summary to the orchestrator — enough to inform
   coordination decisions without bloating the orchestrator context window.
2. Full findings directly to the output pipeline for filtering and delivery.

The orchestrator never receives raw expert output. This is a hard constraint
that keeps orchestrator context lean across multi-expert workflows.

### Control Model And Contracts (implemented — Phase 1 spine)

The orchestrator is a clannon-owned loop: the model is a structured *advisor*
that returns one `OrchestratorDecision` per turn (`answer`, `spawn_experts`,
`call_tool`, or `need_more`); clannon code executes it — enforcing permissions,
routing, and streaming the decision log. The framework never drives the loop.

Implemented contracts (experts, tools, and memory are wired behind ports and are now
**BUILT** — see [../ARCHITECTURE.md](../ARCHITECTURE.md) §4-§5. The **entropy router is
[PROPOSED] — not built**; spawn count is currently whatever the model emits):

- **Decision log:** a structured `DecisionLogEntry` (kinds: hydration, route,
  expert_spawn, tool_call, observation, answer, warning, error), streamed through
  an async sink and mirrored to `ctx.decision_log`. The live stream is delivered
  directly; only the final report buffers through the output filter.
- **Expert two-output split:** experts return a brief `ExpertSummary` to the
  orchestrator; full `ExpertFindings` buffer in `ctx.expert_findings` for the
  output filter.
- **Draft output:** the orchestrator writes an `OrchestratorResponse` to
  `ctx.orchestrator_response`; it never content-blocks.
- **Tool handler:** tools are invoked through a handler that runs a permission
  (`PermissionLevel`) check and records each call on `ctx.tool_calls`; sandboxed
  execution (restrictedpython/Docker, timeout, output cap) is the planned fill-in.
- **Bounds:** `ORCHESTRATOR_MAX_TURNS` / `ORCHESTRATOR_TIMEOUT_S`; the turn cap
  forces a final answer, a timeout fails the stage closed.

## Experts And Sub-Agents

Experts are specialized workers called by the orchestrator.

Examples:

- research expert
- documentation expert
- code expert
- media expert
- citation/source verification expert
- UI/UX expert
- data analysis expert
- platform notification expert

Experts operate under least privilege. They have scoped skills/tools and no
memory handle. Relevant user context may be pushed as inert task data.

## Memory System

Memory is clannon's moat. It lets users keep creating without repeatedly
re-explaining their work.

### Memory Manager

The Memory Manager is a distinct component responsible for proactive context
hydration. It does not wait for the orchestrator to request memory — it pushes
relevant context into the orchestrator's working context before the orchestrator
begins planning, based on the incoming verified request.

Responsibilities:

- retrieve relevant memories across all four tiers
- rank and filter by relevance, recency, and trust level
- enforce the Lagrangian token budget allocation across tiers
- inject the final hydration package into orchestrator context
- curate completed, filter-approved turns with its own bounded LLM
- expose typed, scope-captured search/save tools only to that curator
- classify relevant items into semantic, episodic, or procedural tiers
- enforce deterministic confidence, bounds, dedup, supersession, and provenance
- expose bounded authenticated list/delete operations for archive delivery

The memory layer is reached only through the Manager, the sole implementer of the
`MemoryPort` contract: `hydrate`, `process_turn`, `list_entries`, and
`delete_entry`. Manager is built: real hydration, Lagrangian budgeting,
trust/recency ranking, tool-driven curation, Qdrant writes, and archive operations.
Experts/orchestrator never receive this port. Pipeline memory stages pass prepared
context in and neutral accepted-turn evidence out; authenticated API delivery owns
listing/deletion.

### Lagrangian Memory Budget Allocation

The Memory Manager distributes the available context token budget across memory
tiers using a Lagrangian allocation model. Each tier receives a budget
proportional to its per-query relevance score, subject to a total token
constraint. Formally:

```
maximize  sum_i( relevance_i * tokens_i )
subject to  sum_i( tokens_i ) <= total_budget
            tokens_i >= min_i  for each tier i
```

This ensures high-relevance tiers receive more context without any tier being
starved entirely. Minimum floors prevent a single dominant tier from
monopolizing the budget.

### Memory Tier Definitions

#### Wiki Memory

Highest-trust user-authored memory.

- user-editable `.md` files stored in S3 / Cloudflare R2
- instantly visible to agents
- explicit project/domain knowledge
- overrides inferred memory when conflicts arise
- ideal for specs, preferences, style guides, research notes, project facts

#### Semantic Memory

Durable facts and relationships.

- entities, facts, claims, links between concepts
- user/project/domain relationship graph
- source-backed knowledge when available
- tracks provenance and confidence

#### Episodic Memory

Experiences and events.

- user decisions, prior conversations, completed tasks
- failed approaches, milestones, project history

Episodic memory supports continuity and helps the system remember how work
evolved. It is the non-negotiable baseline tier available to all users
including the free tier.

#### Procedural Memory

Skills, habits, and repeatable workflows.

- user preferences, coding habits, documentation style
- repeated research patterns, orchestration routines, tool-use patterns

Procedural memory is selected by Manager and may enter later turns only as
preselected relevant user context.

### Vector Store Architecture

A single Qdrant instance is used for all memory tiers. Collections are not
created per user. Instead, all vectors are stored in shared collections and
scoped at query time using `user_id` payload filtering. This keeps the
infrastructure simple and avoids collection proliferation.

The `user_id` filter is mandatory and enforced at the Memory Manager boundary —
no other module may construct a raw Qdrant query. **Correction:** the Semgrep CI
build-gate is **PROPOSED — not built** (no semgrep config in repo; CI runs only pytest
+ frontend build). Today the single-door rule, runtime per-hit re-checks, and
`tests/memory_isolation.py` are the guard; the build-gate that would make an unscoped
query a *build failure* is future work (see
[INVARIANT_OWNERSHIP.md](INVARIANT_OWNERSHIP.md) §V.20).

### Memory Tier Access By Subscription Tier

Memory tiers unlock progressively across subscription plans:

| Tier        | Free | Starter ($29/mo) | Pro ($79/mo) | Agency ($199/mo) |
|-------------|------|------------------|--------------|------------------|
| Episodic    | ✓    | ✓                | ✓            | ✓                |
| Wiki        | —    | ✓                | ✓            | ✓                |
| Semantic    | —    | —                | ✓            | ✓                |
| Procedural  | —    | —                | ✓            | ✓                |

Episodic memory is non-negotiable for all tiers. It is the baseline that makes
continuity possible even for free users.

## Token Budget System

### Enforcement Architecture

Token budgets are enforced with two stores:

- **Redis**: real-time atomic decrement on every LLM call. Provides instant
  budget enforcement with no race conditions. Tracks current remaining budget
  per user per billing period.
- **Postgres**: durable budget state. Source of truth for billing, reset
  history, and audit. Synced asynchronously from Redis.

On every LLM call, the system decrements Redis atomically before the call
proceeds. If the budget is exhausted, the call is blocked and the user is
notified. Budget resets are triggered by Stripe `invoice.paid` webhooks, which
update both Redis and Postgres.

### Subscription Token Budgets

Token budgets are per billing period, not per report. This gives users
flexibility in how they use their allocation:

| Plan           | Monthly Token Budget | Target Margin |
|----------------|----------------------|---------------|
| Starter ($29)  | ~2M tokens           | ~35–40%       |
| Pro ($79)      | ~6M tokens           | ~35–40%       |
| Agency ($199)  | ~20M tokens          | ~35–40%       |

Pricing is set to maintain 35–40% margin after model provider costs.

## Session Continuity

Users should not need to start new sessions.

Hot session state lives in Redis or in-memory cache while the model context is
healthy. The system continuously monitors context pressure. When the context
window approaches a defined pressure threshold, clannon:

1. Summarizes low-signal recent turns.
2. Writes durable context to the appropriate memory tiers.
3. Drops ephemeral working state that is already captured in memory.
4. Silently starts a fresh internal model session.

The user experiences this as one uninterrupted workspace.

Hydration for the new session is built by the Memory Manager and includes:

- current task state
- recent high-signal turns
- relevant wiki memory
- relevant semantic facts
- important episodic context
- relevant procedural preferences

Retrieval is selective, ranked by relevance, and trust-aware. Full transcript
replay is never used.

## Output Filter

The output filter is the final gate before delivery. It runs on all final
responses — not on the orchestrator's decision log stream, which is delivered
directly.

The output filter checks:

- policy compliance (safety, content policy)
- hallucination markers and ungrounded factual claims
- citation integrity (claims backed by sources where required)
- schema conformance for structured outputs
- PII exposure in final text
- instruction-following completeness

If the output filter blocks a response, it returns a structured failure with a reason
code, and the pipeline driver runs a **bounded** revision loop —
`FILTER_MAX_REVISIONS = 2` (`backend/foundation/vocab/constants.py:173`), feeding the
reason back (`ctx.filter_feedback`) and re-running the reasoning loop, fail-closed after
the bound (`backend/core/pipeline.py:180-229`). **Correction:** there is **no**
"escalate to a different expert" path in code; that earlier claim is removed.

## Background Jobs And Async Work

Tasks that exceed a reasonable synchronous timeout are routed to background
jobs. This applies to:

- deep research workflows spanning many sources
- large document processing
- batch media analysis
- memory consolidation and compaction
- report generation for complex multi-expert tasks

Background jobs write task state to Redis with a job ID. The user receives
immediate acknowledgment and a progress handle. The dashboard polls or receives
a push notification on completion. Results surface through the same delivery
layer as synchronous responses.

## MCP Integrations

clannon supports MCP (Model Context Protocol) connections for automatic client
and workspace context injection. MCP integrations allow experts to pull live
context from connected tools — project managers, code hosts, document stores,
communication platforms — without the user manually copying context into the
conversation.

MCP integrations are owned by the platform delivery layer. They do not bypass
the sanitization or verification stages — data from MCP sources enters the
pipeline as normalized input and is subject to the same security gates as
user-submitted input.

MCP is a stated product differentiator. It is the mechanism that makes
workflow automation (not just assisted work) possible.

## Demo System

The demo system is fully isolated from the real pipeline.

Architecture:

- Pre-computed outputs generated by powerful frontier models are stored per
  workflow type.
- At demo time, a lightweight cheap model handles surface-level personalization
  (inserting the user's input into the pre-computed structure) without running
  the real pipeline.
- The demo system has no access to real user memory, real token budgets, or
  real expert infrastructure.
- IP-based rate limiting is applied at the demo entry point.
- No signup is required to run a demo.

The demo exists to convert visitors, not to validate the pipeline. Real
pipeline validation happens with actual users post-signup.

## Research Workflow

Research must be source-grounded and citation-aware.

Expected flow:

1. Clarify the research objective when needed.
2. Search or retrieve from trusted sources.
3. Compare recency, authority, and conflicts.
4. Record source metadata.
5. Separate facts, assumptions, and inferences.
6. Produce concise or deep reports as requested.
7. Store durable findings in the right memory layer when appropriate.

High-stakes domains require stricter sourcing, current verification, and safer
language.

## Documentation Workflow

Documentation should be accurate, structured, and useful.

The system should support:

- technical docs
- product docs
- research summaries
- project specs
- API docs
- changelogs
- design docs
- decision records

Wiki memory should act as the user's editable source of truth for persistent
documentation context.

## Coding Workflow

Coding must follow repository conventions.

The coding agent should:

- inspect existing code before changing it
- prefer local patterns
- keep edits scoped
- protect user changes
- run targeted tests
- avoid destructive commands
- explain outcomes clearly

Code work should be integrated with memory so the system remembers project
architecture, decisions, and recurring preferences.

## UI And UX

The default dashboard is the website. It should feel like a serious creative
and research workspace, not a generic chatbot shell.

Core UX requirements:

- persistent project/session spaces
- visible memory/wiki controls
- transparent source/citation views
- task progress and background-job state
- document/code/research workspaces
- notification and message preferences
- clear safety and permission prompts
- platform connection management
- real-time orchestrator decision log visible to user during task execution

The user should feel oriented, not trapped in hidden agent behavior.

## Platform Delivery

Users can interact through the platform of their choice.

The delivery layer should support:

- web dashboard (default)
- email
- messaging platforms
- notifications
- future workspace integrations

Platform adapters do not own reasoning. They translate messages, actions,
notifications, and delivery state into clannon's internal contracts.

Session state is maintained in Redis and is platform-agnostic. A user may
start a task on the web dashboard and receive the result via a messaging
platform notification without any session discontinuity.

## Security Model

Security is layered and explicit:

- intake rejects malformed, oversized, or unsupported input
- sanitizers clean and block dangerous payloads in parallel modality workers
- normalizer prevents lossy or unsupported media handoff
- verifier runs LLM-based semantic screening and structured routing decisions
- orchestrator uses explicit tool/expert permission policies under least-privilege
- tools run in constrained, sandboxed environments
- output filter checks final content before delivery
- memory writes pass through policy and trust rules
- MCP data enters through the same sanitization and verification gates as
  user input — it does not bypass security stages
- content retrieved by experts mid-execution (web pages, fetched documents, tool
  outputs) is untrusted input and re-enters sanitization + verification before it
  can influence reasoning or be written to memory; it is never treated as trusted
  simply because an authorized expert fetched it
- session identity (`user_id`, plus `client_id`/`project_id` where applicable) is
  set once at the authenticated entry point, travels in Flow context, and is the
  sole source of identity for every downstream memory and tool call — never
  re-derived from request content, retrieved content, or model output
- Postgres RLS scopes rows by `user_id` via a transaction-local session variable
  (`SET LOCAL` inside a transaction, never connection-level `SET`), so pooled
  connections cannot leak one tenant's scope into another's query

Security failures block. Infrastructure and configuration failures fail hard.
Warnings proceed only when the downstream layer can safely handle the risk.

## Quality Model

Quality is enforced through:

- structured outputs with schema validation at every stage
- deterministic pre-checks before LLM calls
- source verification and citation integrity in the output filter
- focused expert routing (specialists, not one oversized prompt)
- memory provenance and confidence tracking in semantic memory
- tests around contracts and safety boundaries
- user-editable wiki truth as the highest-trust knowledge source
- output filter as the final quality gate before delivery

Paying users should not feel like they are debugging the system.

## Speed Model

Speed comes from:

- deterministic checks before LLM calls
- cached hot session context in Redis
- selective memory retrieval via Lagrangian budget allocation
- async/background jobs for long-running tasks
- small, fast verifier and filter models
- specialized experts instead of one oversized prompt
- parallel modality workers in the sanitization layer
- provider/model routing through `models.yaml`
- compact context hydration via the Memory Manager instead of full transcript
  replay
- entropy-based expert spawning to avoid over-spawning on focused queries
  (**[PROPOSED] — not built**; today spawn count is whatever the model emits)

## Infrastructure Summary

| Component         | Local Dev              | Cloud / Production         |
|-------------------|------------------------|----------------------------|
| Backend           | FastAPI + PydanticAI   | Railway                    |
| Frontend          | —                      | Vercel                     |
| Primary DB        | SQLite                 | Supabase / Postgres + RLS  |
| Session / Budget  | Redis (local)          | Upstash Redis              |
| Vector Store      | Qdrant (Docker)        | Qdrant Cloud               |
| Embeddings        | fastembed nomic-embed-text (local ONNX) | hosted-API profile (PROPOSED) |
| Wiki File Storage | Local / S3-compatible  | Cloudflare R2              |
| Billing           | —                      | Stripe                     |
| Virus / YARA scan | ClamAV + YARA (local)  | ClamAV + YARA              |

## Final Principle

clannon's moat is not a model, framework, or UI surface. The moat is secure,
high-quality continuity: a memory-native agentic workspace where users can keep
researching, writing, coding, and creating without restarting context or
managing infrastructure.

The irreducible human contribution in building clannon is diagnosing which
architectural lever maps to which failure mode. Implementation is automatable.
Judgment about what to build is not.
