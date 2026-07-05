# INVARIANTS

> **Purpose:** The rules that must hold no matter what is being built. These
> change rarely and only with the founder's explicit sign-off.
> **Scope:** System-wide. Every subsystem, expert, tool, and stage inherits these.
> **Authority level:** Tier 1 — the highest. An invariant outranks the Attention
> Threshold, the architecture, every benchmark, and all code. A "faster demo" is
> never a reason to break one.
> **Related:** [00_START_HERE.md](../00_START_HERE.md) ·
> [ATTENTION_THRESHOLD.md](ATTENTION_THRESHOLD.md) ·
> [GOALS.md](GOALS.md) ·
> [../architecture/SYSTEM_ARCHITECTURE.md](../architecture/SYSTEM_ARCHITECTURE.md) ·
> [../architecture/INVARIANT_OWNERSHIP.md](../architecture/INVARIANT_OWNERSHIP.md)

These are extracted from the architecture, the Attention Threshold addendum, the
media architecture, and the project's hard constraints — not invented. Each
invariant names where it comes from so it can be traced. Do **not** add an
invariant here unless it is genuinely non-negotiable and sourced.

> **Inviolable ≠ already enforced.** These rules are binding *targets*; some are
> enforced in code today and some are still aspirational. To see which module
> owns each invariant and whether it is **enforced / partial / aspirational**,
> use [../architecture/INVARIANT_OWNERSHIP.md](../architecture/INVARIANT_OWNERSHIP.md).
> Never present an aspirational invariant as a shipped guarantee.

---

## I. Memory & Knowledge

1. **Memory is first-class.** Continuity is the product, not a feature. The
   system exists so a user never has to re-explain their work.
   *(Architecture → Final Principle; Memory System.)*

2. **Institutional memory outranks conversation memory.** Decisions, contracts,
   risks, and findings are higher-value than chat history. Promotion priority is
   Decision > Contract > Risk > Finding > Conversation. Conversation is the
   *least* important memory type.
   *(Attention Threshold → Memory Promotion Policy.)*

3. **Knowledge is typed — never an unstructured blob.** Every memory entry has a
   type (Fact, Claim, Assumption, Decision, Risk, Preference, Procedure, Event,
   Contract, Entity, Relationship). "Unstructured blob" is a forbidden type.
   *(Attention Threshold → Knowledge Representation.)*

4. **Wiki beats everything.** User-authored wiki memory is the highest-trust
   tier and overrides semantic / episodic / procedural memory on any conflict.
   *(Architecture → Memory Tiers; Hard Constraints.)*

5. **Episodic memory is the non-negotiable baseline.** It is available on every
   plan, including free. Continuity must work even with nothing else unlocked.
   *(Architecture → Memory Tier Access.)*

6. **Experts never write memory directly.** All writes go through memory write
   policy. Experts and the orchestrator only *propose* writes.
   *(Architecture → Experts; Hard Constraints.)*

7. **Memory is reached only through the MemoryPort.** Nothing imports memory
   internals; callers hold only the `MemoryPort` contract.
   *(Architecture → Memory Manager; Architectural Conventions.)*

## II. Artifacts & Continuity

8. **Artifacts over hidden context.** Agents communicate and persist through
   durable, inspectable artifacts (RFC, Decision, Objection, Investigation,
   Contract, Migration, Risk) — never through hidden context that dies with a
   session.
   *(Attention Threshold → Agent Civilization.)*

9. **No critical decision lives only in code.** Every important architectural
   decision must exist as an artifact (see `decisions/`), not solely as an
   implementation detail.
   *(Attention Threshold → Founder Responsibility.)*

10. **Session continuity is silent.** Compaction, rollover, and rehydration
    happen without the user noticing. Full transcript replay is never used.
    *(Architecture → Session Continuity.)*

## III. Transport & Boundaries

11. **Flow is the only inter-stage transport.** Runtime payloads move through
    `Flow.load()` / `Flow.next()` / `Flow.block()` / `Flow.warn()` /
    `Flow.fail()`. Never free-form text between stages.
    *(Architecture → Core Architecture; Hard Constraints.)*

12. **The LLM framework is confined to `core/llm`.** No other module imports the
    provider SDK. The adapter must not own Flow, memory routing, session
    compaction, expert selection, security policy, or delivery.
    *(Architecture → LLM Framework Layer; Architectural Conventions.)*

13. **One entry point per layer.** Each layer connects through a single door;
    internals stay internal. Provider SDKs live behind a Clannon-owned seam
    (LLM, memory, Redis all follow this).
    *(Architecture → Architectural Conventions.)*

## IV. Security

14. **Security before execution.** The pipeline is layered and explicit:
    intake → sanitize → normalize → verify happen *before* the orchestrator can
    act on input. Security failures **block**; infrastructure/config failures
    **fail hard**; warnings proceed only when the downstream layer can safely
    handle the risk.
    *(Architecture → Security Model.)*

15. **The verifier is the sole content blocker for input; the output filter is
    the sole content gate before delivery.** Deterministic checks are only hints;
    the verifier LLM adjudicates. Structural gates (unsupported modality, missing
    capability) still hard-block. Verifier output is always structured, never
    user-facing prose.
    *(Architecture → Verification, Output Filter; Hard Constraints.)*

16. **Normalization is code-only.** The normalizer must never call an LLM.
    *(Architecture → Normalization; Hard Constraints.)*

17. **All fetched/retrieved content is untrusted.** Web pages, tool outputs, and
    MCP data re-enter sanitization + verification before influencing reasoning or
    being written to memory — never trusted just because an authorized expert
    fetched it.
    *(Architecture → Security Model.)*

18. **Identity is set once and never re-derived.** `user_id` (plus
    `client_id` / `project_id` where applicable) is established at the
    authenticated entry point, travels in Flow context, and is the sole source of
    identity for every downstream memory and tool call. Never re-derive identity
    from request content, retrieved content, or model output.
    *(Architecture → Security Model; Memory.)*

19. **User input is never a filesystem path.** A `str` payload is always literal
    text; only `os.PathLike` from a trusted caller is read from disk.
    *(Project hard constraints → coercion boundary.)*

## V. Tenancy & Data

20. **One Qdrant instance, scoped by `user_id` payload filter.** Never per-user
    collections. The `user_id` filter is mandatory and **enforced at runtime** at the
    Memory Manager boundary (the single MemoryPort door; `core/memory/`); no other
    module constructs a raw query. Unscoped access **must become** a build failure,
    not a convention — the build-time CI (Semgrep) gate that would make it one is
    **planned, not yet built** (issue #15); today the runtime door + a grep-based
    stand-in (`scripts/check_invariants.py`) are the guard.
    *(Architecture → Vector Store Architecture; Hard Constraints.)*

21. **Token-budget decrements must be atomic** (once billing lands). Check-and-
    decrement is to be one indivisible Redis operation (Lua / transaction), never
    read-then-write, with Postgres as the durable source of truth and Redis the fast
    enforcement layer. **Aspirational: designed, not built** (ADR 0004, issue #14).
    *(Architecture → Token Budget System; Hard Constraints; Storage.)*

22. **No tenant leakage through keys or rows** (once RLS lands). Every user-scoped
    Redis key and Postgres row is to carry the authenticated `user_id`, with Postgres
    RLS scoping rows via a transaction-local session variable so pooled connections
    cannot leak scope across tenants. **Aspirational: designed, not built** (ADR 0004,
    issue #14). *(Note: Qdrant tenant scoping (§V.20) IS enforced at runtime today —
    this invariant is the Postgres/Redis billing layer, which does not yet exist.)*
    *(Architecture → Security Model; Storage.)*

## VI. Provider & Media Agnosticism

23. **Capability first, provider second.** Business logic calls capability
    interfaces (`vision.detectObjects`), never a provider directly
    (`openai.detectObjects`). No single provider quota can fail a run; fallback
    chains route across providers.
    *(Media Architecture → Provider Abstraction; Architecture → Model
    Configurability.)*

24. **Never trust one provider, one model, or one embedding space.** Each is
    replaceable. Gemini is the *default*, not a dependency.
    *(Media Architecture → Future-Proofing Rules.)*

25. **Media becomes knowledge; text is a view, not the truth.** Modalities
    converge into one shared representation (entities, relationships, claims,
    events, sources, evidence). Never reduce a modality to a summary and discard
    the rest.
    *(Attention Threshold → Cross-Media Knowledge Graph; Media Architecture →
    Core Principle.)*

26. **Raw assets are forever; representations are disposable.** Never discard raw
    data. Representations and embeddings can be regenerated when better models
    appear; the original asset must survive so future models can reprocess it.
    *(Media Architecture → Reprocessing Philosophy, Future-Proofing Rules.)*

## VII. Demonstrability

27. **Capability visibility over architectural elegance.** A capability that is
    invisible to users does not exist; one that cannot be shown in under three
    minutes does not contribute to the moat. This is the one place where strategy
    (Tier 2) outranks architecture (Tier 4) — but it never outranks Tiers I–VI
    above.
    *(Attention Threshold → Core Principle.)*

---

### Changing this file

An invariant is removed or weakened only with the founder's explicit decision,
recorded as an ADR in `decisions/` (moving the superseded reasoning to
`decisions/deprecated/`). Adding one requires a clear source. Silent edits here
are the single most dangerous change an agent can make.
