# Batch Architecture — `[PROPOSED]`

> **Status: `[PROPOSED]` — design-only, nothing built.** A new structural layer
> between the central orchestrator and the flat expert roster. Owner-authored
> (mission `proposals/to-backend/BATCH_ARCHITECTURE.md`, 2026-07-04); it completes
> and supersedes the intent behind the Premium-Parity mission's Phase 5 capability
> work. Extends — does not reopen — the locked decisions in
> `docs/ARCHITECTURE.md`: Mission Engine (§6, PROPOSED), sole-broker memory
> (§7.3, BUILT at one tier), entropy-as-advisory (§7.2, PROPOSED).
> **Build discipline: propose-first + stability-first (see §Prime Directive).**
> Nothing here may be implemented before its design sub-spec is proposed and the
> foundation it sits on is verified stable.

---

## 1. Why (the missing layer)

Today: one central orchestrator drives a **flat roster** of experts as native
tools (`registry/capabilities/handler/`). This is fine for single-domain turns but
does not scale to a broad, weeks-long mission that spans genuinely different kinds
of judgment (engineering + research + media + security + docs at once) without the
orchestrator's context exploding. The **batch** is the missing grouping layer.

## 2. Structure `[PROPOSED]`

- **One central orchestrator** — today's orchestrator, evolved into a *coordinator
  of coordinators* (task-graph state + batch statuses + brief summaries only, never
  full transcripts — mirrors the existing two-output split).
- **Multiple batches.** Each batch = **one batch orchestrator + a set of experts**
  in that batch's domain, each expert equipped with the precise domain tools it
  needs. Group by *kind of judgment*, not arbitrarily. Candidate batches:
  engineering/code, research, media, security, documentation.
- **Baseline general-purpose tools at BOTH orchestrator tiers** (file read, simple
  search, basic web fetch — NOT domain-expert-tier tools), so an orchestrator can
  cheaply handle a trivial task itself instead of forcing a spawn. Rule: no
  delegation when the orchestrator handling it directly is cheaper and faster.

## 3. Delegation logic `[PROPOSED]` (central orchestrator's new core decision)

- **Trivial single-domain** ("write code to do X") → route directly to one batch
  (now it depends on that batch's orchestrator on whether it uses just one expert or multiple, central orchestrator doesn't care after it routes the work to a batch). No cross-batch coordination.
- **Broad** ("build a SaaS that does X") → the central orchestrator decomposes into
  sub-tasks, identifies which batches are needed, sequences/parallelizes them, and
  coordinates hand-offs. Coordinator of coordinators, not a micromanager. 
    > **Owner's description**:
    >
    > If you didn't think of it, this is also the real usecase for mission engine,
    > mission engine is what makes breaking down larger goal into small sub tasks possible
    > if the goal is really broad and big, we can make the mission engine non deterministic
    > meaning llm calls of its own, and the central orchestrator just delegates the broad
    > work to it and central orchestrator should need to know whether the task is broad or trivial
    > and even if doesn't break goal into sub tasks and route to the batches (yes, broad task and works broken down into pieces by mission engine means the engine would feed the batches and let the orchestrator know)

    > Why this way: The central orchestrator is the only user facing thing so it's context window is precious and since it already has an idea of what it did, like delegating task to mission engine,
    > and what did the mission engine do, what batches were engaged etc etc, and if needed ,it also has the ability to know the things in deep from the mission engine or a separate helper whose only job is to get the context for central orchestrator, so this way, central orchestrator doesn't lose anything and preservs context window too, win win for us.

- **Entropy-as-advisory at the batch tier**: compute domain-similarity signals
  across *batches* (not just experts), surface as evidence, let judgment decide
  routing — never a hard math gate (entropy-as-advisory — docs/ARCHITECTURE.md §7.2).

## 4. Two-tier sole-broker memory `[PROPOSED]` (extends sole-broker, does NOT violate it)

The sole-broker principle applies at **two tiers**, still one principle:

- **Central orchestrator** — full memory access (unchanged from today's BUILT
  sole-broker).
- **Batch orchestrator** — its own domain/work-scoped memory **plus a deliberately
  thin cross-batch awareness slice**: just enough summary of what other batches are
  doing/have concluded to recognize "this belongs to batch Y — delegate/flag." NOT
  full access to other batches' detail.
- **Experts** — unchanged sole-broker: stateless, no memory grant, hydrated by
  **their batch orchestrator** (or `need_context` to their batch orchestrator, not
  the central one).
- Broker chain: central brokers for batch orchestrators; batch orchestrators broker
  for their experts. **No new memory path bypasses the door.**

> **Required sub-spec before any build:** the "minimal cross-batch awareness slice"
> is a **new memory contract** — what goes in it, how it stays small, how it
> refreshes. Must be designed as an explicit extension of
> `docs/architecture/memory/ROBUST_MEMORY_ARCHITECTURE.md` and **proposed first**.

## 5. Context-window discipline across batches `[PROPOSED]` (the hard problem)

- Context passed to a batch is **scoped to that batch's task**, never a full dump.
- The central orchestrator's working context stays lean (task-graph + statuses +
  brief summaries; full findings go to the appropriate sink — the existing
  two-output split, generalized).
- **Compaction** for long-running work: older low-signal context is summarized,
  durably written to memory, and dropped from hot context — now **per-batch and
  across the whole mission**, not just per-session (generalizes the session-
  continuity design, itself PROPOSED / Phase E).
- A **fresh session days later** must resume a batch's / the mission's state from
  durable memory + the mission graph, never from conversation replay. This is the
  direct link to **CB1** (persistent cross-session memory) and the **Mission
  Engine** (docs/ARCHITECTURE.md §6): batches plug into its persistent state-machine,
  **not** a separate parallel system.

## 6. Long-horizon operation `[PROPOSED]`

The point of batches + Mission Engine + compaction: Clannon works a broad mission
for weeks and still delivers *what was actually intended*, not a drifted/forgotten
version. The mission's original intent + success criteria (the Mission Engine)
remain the anchor it re-checks against after many compactions and restarts.
**Anything that could break under a week+ mission (context loss, drift, a forgotten
original ask) is a stability BUG, not a future improvement** (see §Prime Directive).

  > **Owner's thoughts:**
  >
  > Relating memory to this: The mission engine also has it's own memory consisting of only what it did,
  > and what feedback and response it got from orchestrator or batch orchestrators, so that we dont lose any context of why the goal was divided and composed like x instead of y,
  > all without bloating the context window where matters, the central orchestrator doesn't know what mission engine knows internally, it just knows what that it (orchestrator) delegated task to it
  > and what mission engine did in response and what happens afterwards and a short summary on the reasoning, so orchestrator can reason about why something was done, all while keeping context window lean

## 7. How batches change the V1 benchmark paths

(Reflected in `docs/benchmarks/V1_GAP_ANALYSIS.md`.)
- **CB2 Large Repo Understanding** — a natural **engineering batch**: expert(s) +
  heavy tools (AST-aware search, dependency-graph traversal, precise patch-apply)
  that *navigate* rather than *ingest*, working on codebases far larger than any
  context window (design target: precise navigation + precise edits in ~30M-line C
  without breaking anything). This is the batch layer's flagship justification.
- **CB6 Multi-Agent Consistency** — tested by whether batches stay contract-
  compatible with each other and the central orchestrator: the same discipline as
  the frontend/backend Integration Contract, applied *internally between batches*.
- **CB1 / EB2** — the persistence that makes weeks-long batch-coordinated missions
  possible at all.

## 8. Build state & sequence (all `[PROPOSED]`; build bottom-up, verify each layer)

Nothing below is built. Each step is propose-first and gated by a stability check
of the layer beneath it:

0. **Stability audit** of the foundations batches sit on — orchestrator loop,
   capability handler, sole-broker memory door, the gate chain — *before* any batch
   code (per §Prime Directive).
1. **Mission Engine** (docs/ARCHITECTURE.md §6, PROPOSED) — the persistent state-machine batches plug
   into. Prerequisite; batches are not a parallel system.
2. **Cross-batch awareness memory contract** (§4 sub-spec) — propose as a
   ROBUST_MEMORY extension.
3. **Batch orchestrator** abstraction + baseline general-purpose tool set at both
   tiers + the entropy-advisory batch-routing signal.
4. **Per-batch experts + domain tools** (decomposition discipline, §Decomposition).
5. **Compaction across batches + mission** (generalizes session continuity).

## Prime Directive — stability before new surface area (standing rule)

Before building ANY new capability: verify everything already BUILT is stable,
correct, efficient — *every line, logic, syntax*, not just "tests pass." Standing,
not a one-time gate:
- Before a new sub-task, sanity-check the piece it sits on. Something shaky/half-
  done underneath ⇒ STOP, fix or flag the foundation first. Never layer new
  capability on a wobbly base.
- "Stable" = correct under normal AND edge input, fails closed/honest on faults
  (the security invariants — docs/ARCHITECTURE.md §8), has a test proving it, not just the happy path.
- A big foundation fix is proposed and absorbed into the plan as a prerequisite,
  never done silently or skipped.
- Recursive: a new expert on a new tool on a shaky hook is three layers of risk.

## Decomposition discipline — required first move for every capability

1. Define what the capability MEANS in concrete, testable terms before any code.
2. Choose the shape: small/narrow → one expert + a few scoped tools; big → one
   expert + multiple heavy tools; very broad (genuinely different reasoning) →
   multiple experts + tools under a batch orchestrator. Test: one coherent domain
   judgment (→ one expert, better tools) vs genuinely different expertise per phase
   (→ multiple experts).
3. Write the decomposition down before implementing (design note in the relevant
   `docs/` file).
4. **Tools are CODE** — deterministic, fast, no LLM, narrowly scoped (parse, walk,
   patch, search, extract). **Experts are LLM-backed** — judgment, synthesis,
   deciding which tools to use. Never blur the line.

## Security (unchanged, non-negotiable)

user_id scoping at the Memory Manager boundary; sole-broker (now at two tiers);
mid-execution retrieved content re-enters sanitization; rejected drafts never touch
memory. **Batches do not bypass any of these.** Any latency/premium optimisation
that would weaken them ⇒ STOP and propose.

## Authoritative references

`docs/ARCHITECTURE.md` (locked decisions: Mission Engine §6, entropy-advisory §7.2, sole-broker §7.3)
(§6 Mission Engine, §7 orchestration/routing, §7.3 sole-broker),
`docs/architecture/memory/ROBUST_MEMORY_ARCHITECTURE.md` (memory contract to
extend), `docs/benchmarks/V1_GAP_ANALYSIS.md` (benchmark paths),
`docs/benchmarks/mission/PHASE_5_capability.md`.
