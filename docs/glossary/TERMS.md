# TERMS — Glossary

> **Purpose:** A single definition for every Clannon-specific term, to prevent
> terminology drift between agents and humans.
> **Scope:** Product/brand names, memory, agents, pipeline stages, knowledge-graph
> and knowledge-representation terms, security terms, and storage/infra terms.
> **Authority level:** Cross-cutting reference (not a tier in the conflict
> ladder). It defines language; it does not decide design. If a definition here
> drifts from a higher-tier doc, the higher-tier doc wins — fix the glossary.
> **Related:** [../00_START_HERE.md](../00_START_HERE.md) and every architecture doc.

When a term has a canonical home, the source is noted in parentheses.

---

## Product & brand

- **Clannon** — the product/brand the user sees. The hosted SaaS for end-to-end
  workflow automation.
- **Vraksha** — the backend engine / codebase. Synonymous with Clannon from the
  internals' point of view ("Vraksha" = tree).
- **Flow** — the structured inter-stage transport schema. The only way runtime
  payloads move between pipeline stages (`Flow.load/next/block/warn/fail`).
  (Architecture → Core Architecture.)
- **Attention Threshold** — the capability bar at which an expert viewer concludes
  Clannon is not a chatbot wrapper or conventional RAG. The near-term north star.
  (vision/ATTENTION_THRESHOLD.md.)

## Pipeline stages

The active pipeline: **intake → sanitize → normalize → verify → orchestrator →
output filter → delivery**, with async memory writes after delivery.

- **Intake** — first raw-input gate: rate limiting, size limits, MIME/modality
  detection, malformed/unsupported blocking. No deep analysis.
- **Sanitizer / sanitization** — security cleanup before reasoning: universal
  ClamAV/YARA pre-gate, then parallel per-modality workers (text/PDF/image/
  audio/video).
- **Normalizer / normalization** — **code-only** (never an LLM) conversion of
  sanitized payloads into a `NormalizedInput` contract.
- **Verifier / verification** — the final input gate: a small fast LLM that does
  prompt-injection screening, malicious-intent classification, and structured
  routing. The sole *input* content blocker; output is always structured.
- **Output filter** — the final gate before delivery on all final responses
  (not on the decision-log stream): policy, hallucination/groundedness, citation
  integrity, schema conformance, PII, instruction-following.
- **Delivery** — the platform adapter layer that returns results (web default,
  email, messaging, notifications). Owns no reasoning.

## Agent terms

- **Orchestrator** — the central reasoning layer; a Clannon-owned loop where the
  model is a structured **advisor** returning one decision per turn, executed by
  Clannon code. Streams a decision log.
- **Expert** — a specialized worker the orchestrator spawns for deep domain work
  (research, code, documentation, media, data analysis, citation, etc.). Reasons
  and produces output; least-privilege; never writes memory directly.
- **Sub-agent** — synonym for an expert/worker spawned beneath the orchestrator.
- **Tool** — a deterministic function experts/orchestrator call to *do one thing*
  (web search, fetch URL, code exec, file read). Tools don't reason.
- **Entropy-based routing / expert spawning** *(PROPOSED — not built)* — the design
  target for deciding how many experts to spawn: **Shannon entropy** over similarity to
  expert domain centroids, surfaced to the orchestrator as an **advisory signal** (math
  informs, the reasoner decides). **Today spawn count is whatever the model emits** (see
  `ARCHITECTURE.md` §7.2).
- **Domain centroid** — a vector representing an expert's domain; the query is
  embedded and compared against these to route.
- **Decision log** — the structured, live-streamed record of what the
  orchestrator is doing and why. Not narrative prose.
- **`DecisionLogEntry`** — one typed decision-log record. Kinds: hydration,
  route, expert_spawn, tool_call, observation, answer, warning, error.
- **`OrchestratorDecision`** — the per-turn advisor output: `answer`,
  `spawn_experts`, `call_tool`, or `need_more`.
- **`ExpertSummary` / `ExpertFindings`** — the expert two-output split: a brief
  summary to the orchestrator (keeps its context lean) + full findings to the
  output pipeline.
- **Registry / Capabilities** — the machinery where tools/experts self-register
  (`@tool` / `@expert`) and are offered to the orchestrator through a single
  guarded, scoped door.

## Memory terms

- **Memory tier** — one of four stores, ordered by trust:
  - **Wiki memory** — highest-trust, user-authored `.md` (R2). Overrides
    everything on conflict.
  - **Semantic memory** — durable facts, entities, relationships, provenance,
    confidence.
  - **Episodic memory** — experiences/events: decisions, prior conversations,
    completed tasks, failures, milestones. The non-negotiable baseline tier.
  - **Procedural memory** — skills, habits, repeatable workflows, preferences.
- **Memory Manager** — sole component that hydrates, classifies, persists, lists,
  and deletes memory. Its own bounded LLM uses internal typed tools; deterministic
  policy owns scope and storage.
- **MemoryPort** — only door to memory. Four methods: `hydrate`, `process_turn`,
  `list_entries`, and `delete_entry`. Reasoning agents do not receive it.
- **Hydration** — assembling the relevant memory package and injecting it into the
  orchestrator's context before planning. Selective and trust-aware; never full
  transcript replay.
- **Second-session moment** — the UX where hydration surfaces proactively when a
  returning user starts work. The UI spec calls it "the product."
- **Lagrangian budget allocation** — distributing the context token budget across
  memory tiers proportional to per-query relevance, subject to a total budget and
  per-tier minimum floors.
- **Trust ordering** — the rule that higher-trust tiers win on conflict
  (wiki > inferred memory).
- **Recency decay** — down-weighting older memories during ranking.
- **Dedup / write policy** — deterministic Manager path that validates,
  deduplicates, attributes, and commits curator-staged actions.

## Knowledge representation & graph

- **Knowledge graph** — the shared representation where every modality contributes
  entities/relationships/claims/events/sources/evidence; the same entity across
  media converges into one node. (Attention Threshold Pillar 2; media architecture.)
- **Universal Asset** — the media model: an asset with raw location, metadata,
  representations, embeddings, entities, relationships, lineage, timestamps.
- **Representation** — an additive, regenerable view of an asset (transcript,
  caption, OCR, AST, layout graph, embeddings…). Representations are disposable;
  raw assets are not.
- **Provenance** — where a fact came from: source, which model produced it, when,
  and confidence. No orphaned facts.
- **Typed knowledge / entry types** — every memory entry has a type; the allowed
  set: **Fact, Claim, Assumption, Decision, Risk, Preference, Procedure, Event,
  Contract, Entity, Relationship**. "Unstructured blob" is forbidden.
- **⚠️ "Artifact" — two distinct meanings; do not conflate.** *(This entry is the
  **canonical** disambiguation — other docs link here rather than restating it.)*
  - **Institutional artifact** *(PROPOSED — no implementation)* — a durable unit
    of inter-agent *reasoning*: **RFC, Decision, Objection, Investigation,
    Contract, Migration, Risk.** The substance of the Agent Civilization pillar.
    Home: `architecture/agents/AGENT_CIVILIZATION.md`. No code yet.
  - **Output artifact** *(built)* — a delivered *file* an expert produces
    (`report.md`, `chart.png`), defined by the `ArtifactStore` / `ArtifactRef`
    contract in `backend/foundation/contracts/artifact.py` and implemented in
    `backend/core/artifacts.py`. Pure output plumbing; unrelated to the
    institutional artifact above.
- **Memory promotion priority** — Decision > Contract > Risk > Finding >
  Conversation. Conversation is least important.
- **Institutional / organizational memory** — memory of decisions, tradeoffs,
  reasoning, and assumptions — distinct from (and higher-value than) conversation
  storage.

## Security terms

- **Prompt injection** — adversarial input that tries to override system
  instructions; screened by the verifier.
- **Memory poisoning** — an attempt to write false/malicious content into memory;
  blocked by write policy + treating fetched content as untrusted.
- **Least-privilege** — every expert/tool gets only the access its task needs.
- **Block / fail / warn** — the three explicit security outcomes: security
  failures **block**; infra/config failures **fail hard**; warnings proceed only
  when downstream can safely handle the risk.
- **Fail-closed / fail-open** — on an enforcement-store outage: fail-closed
  rejects (default for budgets), fail-open allows (often right for rate limiting).
  A conscious tradeoff, never accidental.
- **RLS (Row-Level Security)** — Postgres scoping of rows by `user_id` via a
  transaction-local `SET LOCAL`, so pooled connections can't leak tenant scope.
- **`user_id` scoping** — identity set once at the authenticated entry point,
  carried in Flow context, used as the sole identity for all memory/tool calls;
  never re-derived from content or model output.

## Storage & infrastructure

- **Redis** — fast in-memory store for four jobs: token-budget enforcement, hot
  session state, background-job tracking, rate limiting. Enforcement/cache layer,
  not the source of truth. (Upstash in production.)
- **Postgres** — durable source of truth (billing, state, audit). Supabase + RLS
  in production.
- **Qdrant** — the single vector store for all memory tiers, scoped by `user_id`
  payload filter.
- **Cloudflare R2** — object storage for wiki `.md` files (S3-compatible).
- **Token budget** — per-billing-period token allowance per subscription tier,
  decremented atomically in Redis, durable in Postgres, reset on Stripe
  `invoice.paid`.
- **Session continuity / rollover** — silently summarizing, persisting durable
  context to memory, dropping ephemeral state, and starting a fresh internal
  model session — invisible to the user.
- **MCP (Model Context Protocol)** — connections that pull live external context
  (project managers, code hosts, doc stores) into experts. MCP data enters
  through the same sanitization/verification gates; it never bypasses security.
- **Demo system** — the fully isolated, pre-computed, IP-rate-limited, no-signup
  surface for conversion. No access to real memory, budgets, or pipeline.

## Benchmark & decision terms

- **Benchmark** — an outcome-based capability test (measures what the system can
  do, not how it's built).
- **Critical Benchmark** — required to pass before any outreach.
- **Exceptional Benchmark** — a differentiator; at least one must pass.
- **Outreach readiness gate** — the rule that Clannon is shown only when all
  Critical Benchmarks pass, ≥1 Exceptional passes, and the whole thing is
  demonstrable in one uninterrupted 90–180s run.
- **ADR (Architecture Decision Record)** — a one-decision document capturing
  context, decision, alternatives, and consequences. Lifecycle: proposed →
  accepted → (deprecated); or rejected. (See `decisions/`.)
- **Demonstration pillar** — one of the four capabilities every architectural
  decision should strengthen: persistent organizational memory, cross-media
  knowledge graph, repository intelligence, agent civilization.
