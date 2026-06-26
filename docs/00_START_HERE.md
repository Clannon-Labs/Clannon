# 00 — START HERE

> **Purpose:** The mandatory entry point for any agent or human contributor. Read this first, in full, before touching anything else.
> **Scope:** Orientation, document precedence, and reading order for the entire `docs/` tree.
> **Authority level:** Navigation (defers to the documents it points at). When this file and a Vision document disagree, the Vision document wins.
> **Related:** Everything. This is the index.

---

## What is Clannon

Clannon is a **secure, memory-native platform for end-to-end workflow automation**.

It lets a user hand over a whole job — research, writing, coding, data analysis,
media understanding, verification, and delivery — and get a quality-filtered
result back, without installing local tooling, managing model configuration, or
re-explaining context between sessions.

Three names you will see everywhere:

- **Clannon** — the product / brand the user sees.
- **Vraksha** — the backend engine (the codebase). "Vraksha" and "Clannon"
  refer to the same system from two angles; treat them as synonyms unless a
  document is clearly talking about UI copy (Clannon) vs. internals (Vraksha).
- **Flow** — the structured transport schema every pipeline stage and agent
  communicates through. Never free-form text between stages.

Research was the *first* vertical, not the ceiling. Clannon is a workflow engine,
not "a research tool." Do not pin it to research in code, docs, or UI copy.

## Mission

Clannon is not trying to beat ChatGPT at chatting, Claude at coding, or
Perplexity at search. It is trying to become **the system that remembers,
understands, and evolves projects over time better than any of them** — a
memory-native agentic workspace whose moat is *continuity*, not a model.

The bar it is reaching for is the **Attention Threshold**: a capability level
that makes an experienced AI engineer watching a 3-minute demo conclude "this is
not a chatbot wrapper, this is not conventional RAG." See
[vision/ATTENTION_THRESHOLD.md](vision/ATTENTION_THRESHOLD.md) and
[vision/GOALS.md](vision/GOALS.md).

## Core Principles

High-level only — the binding rules live in
[vision/INVARIANTS.md](vision/INVARIANTS.md).

1. **Memory is first-class.** The product is continuity. Institutional memory
   (decisions, contracts, risks) outranks conversation memory.
2. **Artifacts over hidden context.** Agents communicate and remember through
   typed, durable artifacts — never through hidden context that dies with a
   session.
3. **Security before execution.** Every stage is least-privilege and explicit
   about block / fail / warn. Untrusted input never reaches reasoning unchecked.
4. **Provider agnosticism.** Capability first, provider second. No single
   provider, model, or embedding space may be load-bearing.
5. **Media becomes knowledge.** Text is a view, not the truth. Modalities
   converge into one shared representation; raw assets are never discarded.
6. **Capability visibility over architectural elegance.** A capability that
   cannot be demonstrated does not contribute to the moat.

## Reading Order

Read in this order on first entry to the repository:

1. **`00_START_HERE.md`** (this file) — orientation + precedence.
2. **`vision/INVARIANTS.md`** — the rules that must never be violated.
3. **`vision/ATTENTION_THRESHOLD.md`** — the strategic lens that overrides
   architecture on conflict.
4. **`vision/GOALS.md`** — what Clannon is trying to become and what success is.
5. **`ARCHITECTURE.md`** — the single authoritative, build-state-tagged architecture
   (BUILT / PARTIAL / PROPOSED). Read this for the current architecture and what
   actually runs today. Then **`architecture/SYSTEM_ARCHITECTURE.md`** — retained as
   detailed subsystem canon and the index of every subsystem (defers to `ARCHITECTURE.md`
   on build state).
6. **The relevant `architecture/<subsystem>/` folder** — only the subsystem you
   are about to work in (each folder has a short README entry point).
7. **`benchmarks/`** — the outcomes Clannon must be able to demonstrate.
8. **`decisions/`** — *why* the architecture is the way it is. Read before
   proposing a change, so you don't re-litigate a settled decision.
9. **`glossary/TERMS.md`** — keep open; consult whenever a term is unfamiliar.

## Document Precedence

When two documents conflict, the **higher tier wins** and the conflict is
resolved *upward*. Never resolve a conflict by quietly editing a lower-tier doc
to match your code — escalate it to the owning tier.

| Tier | Authority | Documents | Role |
|------|-----------|-----------|------|
| 1 | **Invariants** | `vision/INVARIANTS.md` | Must never be violated — not even for a demo. Safety, identity, transport, trust ordering. |
| 2 | **Attention Threshold** | `vision/ATTENTION_THRESHOLD.md` | Strategic priority. Supersedes *architecture* decisions when elegance and demonstrability conflict. Never supersedes Tier 1. |
| 3 | **Goals** | `vision/GOALS.md` | What we are building toward. Frames whether a thing should exist at all. |
| 4 | **System Architecture** | `ARCHITECTURE.md` (authoritative, build-state-tagged) → `architecture/SYSTEM_ARCHITECTURE.md` (detailed subsystem canon) | The system-wide design. `ARCHITECTURE.md` is the top authority and wins on build state; `SYSTEM_ARCHITECTURE.md` is retained for subsystem detail. |
| 5 | **Subsystem Architectures** | `architecture/<subsystem>/` | Detail under the system architecture; inherit its rules. |
| 6 | **Benchmarks** | `benchmarks/` | Measure outcomes, not design. They validate; they do not dictate how. |
| 7 | **Decisions (ADRs)** | `decisions/accepted/` | Authoritative record of a single settled decision and its reasoning. Subordinate to Tiers 1–5. |
| 8 | **Implementation docs / code** | `backend/**/README.md`, code comments | Lowest authority. If code contradicts a higher tier, the code is wrong (or the higher tier is stale — escalate, don't assume). |

`glossary/TERMS.md`, `decisions/`, `architecture/ARCHITECTURAL_CONVENTIONS.md`,
and `architecture/INVARIANT_OWNERSHIP.md` are **cross-cutting references**, not a
tier in the conflict ladder: the glossary defines language; ADRs explain
reasoning; conventions say how to place code; the ownership matrix says which
invariants are actually enforced. Conventions are subordinate to the Invariants.

## Navigation Guide — where each concern lives

| If you need to know… | Go to |
|---|---|
| The rules you must never break | `vision/INVARIANTS.md` |
| Why we optimize for demonstrability | `vision/ATTENTION_THRESHOLD.md` |
| What Clannon is becoming / success criteria | `vision/GOALS.md` |
| The whole system, end to end | `architecture/SYSTEM_ARCHITECTURE.md` |
| Pipeline / orchestrator / experts / tools | `architecture/agents/` |
| Memory tiers, hydration, MemoryPort | `architecture/memory/` |
| Media → knowledge, representations, modalities | `architecture/media/` |
| Redis, Qdrant, Postgres, R2, sessions, budgets | `architecture/storage/` |
| Sanitizers, verifier, output filter, threat model | `architecture/security/` |
| Frontend surfaces, states, voice, theme | `architecture/ui/` |
| Repository / deploy layout | `architecture/structure/` |
| Cross-media knowledge graph (Pillar 2) | `architecture/knowledge_graph/` (proposed) |
| Repo-scale reasoning (Pillar 3) | `architecture/repository_intelligence/` (proposed) |
| Agent civilization / institutional artifacts (Pillar 4) | `architecture/agents/AGENT_CIVILIZATION.md` (proposed) |
| How to place / wire new code | `architecture/ARCHITECTURAL_CONVENTIONS.md` |
| Whether an invariant is actually enforced | `architecture/INVARIANT_OWNERSHIP.md` |
| What "good enough to show" means | `benchmarks/` |
| Why a decision was made / what was rejected | `decisions/` |
| What a term means | `glossary/TERMS.md` |

## Attention Threshold pillars → architecture home

The four demonstration pillars (defined in
[vision/ATTENTION_THRESHOLD.md](vision/ATTENTION_THRESHOLD.md)) each have exactly
one architecture home, so a contributor can verify coverage at a glance. "Built"
reflects code that exists today; "proposed" means the home documents a target,
not a shipped feature (see [architecture/INVARIANT_OWNERSHIP.md](architecture/INVARIANT_OWNERSHIP.md)).

| Pillar | Architecture home | State |
|---|---|---|
| 1 — Persistent Organizational Memory | [architecture/memory/](architecture/memory/) + `backend/core/memory/ARCHITECTURE.md` | base memory built; institutional/decision layer **PROPOSED — no implementation** |
| 2 — Cross-Media Knowledge Graph | [architecture/knowledge_graph/](architecture/knowledge_graph/) | **PROPOSED — no implementation** |
| 3 — Repository Intelligence | [architecture/repository_intelligence/](architecture/repository_intelligence/) | **PROPOSED — no implementation** |
| 4 — Agent Civilization | [architecture/agents/AGENT_CIVILIZATION.md](architecture/agents/AGENT_CIVILIZATION.md) | runtime built; artifact protocol **PROPOSED — no implementation** |

## What you must never do without escalating

- Change anything in `vision/INVARIANTS.md`.
- Resolve a conflict by editing a lower-tier doc to match code.
- Introduce a new architecture decision without recording it in `decisions/`.
- Treat any single provider/model/embedding as irreplaceable.

If a higher-tier document appears wrong or stale, **say so explicitly to the
founder** — do not silently override it.
