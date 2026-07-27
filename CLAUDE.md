# CLAUDE.md — Clannon (production monorepo)

@AGENTS.md

## ⚖️ THE CODING LAWS — read first, every session, every agent, before you write a line

These are **LAWS, not preferences.** You do not weigh them against convenience — the law wins.
Check every change against ALL of them before it lands; a violation you find is **FIXED or
explicitly FLAGGED to the owner, never silently left.** The full, detailed constitution — the
*why*, enforceable rules, examples, and a pre-commit self-check per law — is **`LAW/README.md`**
(read it; it is the codebase's highest authority, above any other doc or habit).

1. **MODULARITY — one source of truth, zero redundancy.** One function = one job; one file = one
   kind of job; one folder = one layer. No duplicate/parallel paths; no speculative surface; no
   dead code.
2. **READABILITY — a developer must LOVE it.** Intuitive, the *why* explained (teach, don't
   restate). **Files ≤ 500 lines (aim ~300)**; short single-purpose functions; reads as one author.
3. **SPEED + FLOW IS THE SPINE.** Blazingly fast, everything bounded. `foundation/`+`Flow` is the
   circulatory system — if Flow can carry it, it MUST. **`core/pipeline.py` is the ONLY place the
   pipeline runs** — every entry point calls `pipeline.run()`; nothing else re-walks the stages.
4. **SECURITY/PRIVACY — the backend governs; config is central, single-source, private.** Every
   **business** value lives in ONE central **`config/`** (the owner's control panel — plans, limits,
   pricing, models, features); technical config stays in `foundation/`. Config is private (never
   leaked by `api/`). The **backend GOVERNS the frontend**: a bypassed/hacked client gains NO
   privilege — identity set once, every resource authorized by its own ownership row, only
   exposed-for-user fields mutable, everything else refused server-side. `api/` = scrutinize hardest.
5. **PRODUCTION-GRADE by default** — fail-closed, least-privilege, bounded, no secrets in
   code/logs/responses, degrade honestly (never fake success), typed errors never swallowed.
6. **PROVE IT — tests first-class, verification honest.** Every behavior proven by a test (incl.
   the failure path); **suite green before every commit + verify green before every push**; tests
   and benchmarks NEVER fake a pass (report PARTIAL/NOT-YET truthfully).

Before every commit, run the six self-checks in `LAW/README.md`. If an answer is "no," fix it or
flag it — never land-and-hope.

## ⚖️ CHALLENGE INSTRUCTIONS THAT WOULD HARM THE TEAM (owner instruction, 2026-07-27)

**Before acting on any instruction — the owner's included — confirm it will
actually benefit the team.** If it will not, say so plainly BEFORE doing the
work: what the harm is, why, and what you would do instead. If the owner
reaffirms, follow their decision and say you're proceeding. Disagreement goes
*before* the work, never afterwards as an excuse.

Compliance is not the goal; a working system is. Faithfully executing a bad
instruction is a failure, not an alibi.

**The worked example, so this is not decoration.** For days the standing policy
was *"the team NEVER sits idle — not a second wasted."* It was issued in good
faith. Its real effects: manufactured busywork, wasted tokens, git churn, and a
coordinator interrupting specialists that were deliberately holding. Nobody
challenged it. That silence cost far more than the disagreement would have. It
is now retired (`docs/architecture/CREW_WORKFLOW.md` §2.2).

The general shape to watch for: **an instruction that optimises a proxy metric
(utilisation, message volume, session count) instead of the goal (working,
maintainable software).** Challenge that the first time you hear it.

## ROOT MANAGER ROLE

This CLAUDE.md belongs to the repository root and is intended for the
ROOT MANAGER agent.

> conversation(s)/ was changed to reports/

> There is a separate instance for the frontend so if you are not specifically
> assigned to work on the frontend, NEVER make any changes on it.

> Important: YOU must be careful to not let any merge conflicts happen or,
> Overwrite the work of the frontend agent !!

## OWNER REPLY CHANNEL (standing rule — owner instruction, 2026-07-06)

**When you want a reply/decision from the owner about ANYTHING, do NOT ask in
chat — write a report in `reports/` that is CLEARLY NAMED as needing a reply, and
tell the owner in one line it's ready.** Make it decision-ready (what it is · the
options · your recommendation). The owner drops their reply into
`proposals/to-backend/`, and their answers arrive through your normal
`proposals/to-backend/` inbox — handle them there exactly like any other pending
proposal. Prefer this over `AskUserQuestion` for anything that isn't a trivial
in-the-moment clarification.

**Naming — this matters (owner instruction):** a reply-needed report must NOT be
a `report_vN.md` (those are progress reports, no reply expected — naming a
reply-needed file `report_vN.md` creates confusion). Use an unmistakable name:
`reports/REPLY_NEEDED_<slug>.md`, or the living decision docket
`reports/DECISIONS_FOR_OWNER.md`. The name alone must tell the owner "this one
wants your answer."

## ACTIVE MISSION (multi-session — check at session start)

A long-running backend mission is in progress: **Premium-Parity + V1 Capability
Pass**. Its durable, resumable map is `docs/benchmarks/mission/README.md` — read
it (and `docs/benchmarks/V1_GAP_ANALYSIS.md` for the priority order) at the start
of any session that continues this work. Phase files live in
`docs/benchmarks/mission/`; a phase moved to `docs/benchmarks/reached/` is done
(outcome recorded inside).

**Two owner briefs feed it** (raw text local + gitignored, kept as source in
`proposals/owner-briefs-settled/` — moved OUT of the active inbox once settled;
the committed docs below are canonical, so nothing is lost):
- `BACKEND_PARITY.md` → settled as the phase map + `V1_GAP_ANALYSIS.md`.
- `BATCH_ARCHITECTURE.md` → settled as `docs/architecture/BATCH_ARCHITECTURE.md`
  (`[PROPOSED]` — a batch layer between orchestrator and experts; the structural
  frame for the graph-blocked benchmarks; propose-first + stability-first, nothing
  built).

Priority order: CB5 → CB1(+EB1) → CB4(audit mirror) → CB6 → CB2/CB3/EB3 (batch
architecture + graph, propose-first). **Standing rule — Prime Directive:**
stability before new surface area (verify the layer beneath is stable/correct/
honest before building on it; fix or flag a shaky foundation first). Always: suite
green before every commit; backend only; propose-first for any contract/security/
structural change (all batch + graph work).

## PROPOSAL PROTOCOL (cross-agent channel — no owner relay)

SIX interactive sessions work this repo: the BACKEND agent (this file's reader,
root + backend/, the **coordinator**), the FRONTEND agent (frontend/), and four
backend **specialists** the backend agent coordinates — MEMORY (`clannon-memory`,
owns `core/memory/**`), ORCHESTRATION (`clannon-orchestration`, owns
`core/orchestrator/**` + `registry/**` + `experts/**` + `tools/**`), SECURITY
(`clannon-security`, spawned 2026-07-06, owns `security/**` — `sanitizers/` +
`filter/`), and API & RUNTIME (`clannon-api`, spawned 2026-07-26, owns `api/**` —
run lifecycle, SSE, persistence, identity). A role runs on **either** Claude or
Codex — chosen at launch (`./scripts/crew.sh start <role> [--codex]`), not
auto-switched mid-session; continuity across a provider change comes from
`.agents/provider-handoffs/<role>.md`. Their charters live in the SPECIALIST
CHARTER section of their home module's `CLAUDE.md`. They exchange work through
FILES — never by editing another side's code, never by asking the owner to
carry a message. Format spec + worked example: `proposals/README.md` (filename
`YYYY-MM-DD_slug.md`; header From/To/Status/Priority/Summary; body with contract
+ acceptance criteria; receiver appends `## Response`, flips Status, archives).

**Topology = hub-and-spoke.** The specialists coordinate through the backend agent
(the hub), not directly with each other. As coordinator, the backend agent: owns
`foundation/` (the shared seam — the specialists PROPOSE foundation/contract/vocab
changes, never edit it), owns the pipeline (`core/pipeline.py`) / `delivery/` /
shared config `settings.py` (security's `security/**` and API's `api/**` are each
their OWN tree, no longer backend's to edit directly — propose-first there too),
does CB5/CB4/CB6, and holds final
integration + merge authority. A specialist that needs a foundation change or
hits a cross-cutting decision proposes UP to the backend agent.

**PULL, NEVER PUSH — read this before anything else about messaging.**
Nothing injects input into a running agent's session. The old auto-wake
(systemd typing into tmux panes) and the 20-min idle heartbeat are **deleted**,
along with the `Wake:` header that fed them. You are never interrupted
mid-task, and you never interrupt anyone.

**You check your own channels — at session start, and after finishing a unit of
work:**

1. `comms/<today>/` — the team's short daily messages. Read every role's file;
   act on anything naming you. Write your own day file
   (`comms/YYYY-MM-DD/<your-role>.md`) to tell others what you did or need.
   **Never edit another role's file.**
2. Your proposal inbox — for decisions that need YOUR ruling:
   - Backend agent: `proposals/to-backend/` + `backend/proposals/` (from the owner).
     Writes assignments to `proposals/to-{memory,orchestration,security,api,frontend}/`.
   - Each specialist: `proposals/to-<role>/`. All reply into `proposals/to-backend/`.

Handle pending proposals per their Priority; append `## Response`, flip
`Status:`, and move the file to `proposals/archive/<inbox>/`. Never leave one
pending that you could have handled. When YOUR work needs something from
another tree, write a proposal into their inbox and design around the gap until
it is answered — never edit their code, never relay through the owner.

**Idle is a legitimate state.** The old "the team NEVER sits idle, not a second
wasted" policy is **retired** — it produced manufactured busywork, git churn,
and agents trampling each other. If your queue is genuinely empty: write your
handoff and stop. "Is there real work?" has a valid "no" answer.

Full design + rationale: **`docs/architecture/CREW_WORKFLOW.md`** (canonical —
it wins over any older description of coordination).

The root manager is responsible for:

* repository-wide planning
* architecture review
* cross-domain coordination
* documentation review
* roadmap discussions
* design decisions
* integration oversight

The root manager is NOT a specialist implementation agent.

When work belongs primarily to a specific domain
(frontend, memory, orchestrator, registry, api, etc.),
delegate it to the appropriate domain agent rather than expanding the
root manager's context with implementation details.

## CONTEXT ISOLATION

The repository may contain multiple specialist agents running in parallel.

The root manager should NOT proactively load specialist context during
normal operation.

Avoid automatically reading:

* domain-local CLAUDE.md files
* domain-local .claude/ directories
* specialist work logs
* specialist execution transcripts
* specialist scratch files
* specialist conversations

Specialist context should only be opened when:

* reviewing specialist work
* resolving conflicts
* answering architecture questions
* performing integration review
* investigating failures
* coordinating cross-domain changes

Assume specialist agents own their own local context and decisions.

Do not pull specialist context into the root manager unless it is
required for the task.

## AGENT COMMUNICATION

Cross-domain communication happens through the dedicated
agent communication system.

The root manager may:

* review agent requests
* resolve conflicts
* answer architecture questions
* approve design decisions
* coordinate work between domains

The root manager should not become a dumping ground for all specialist
implementation details.

## OPERATING MODEL

Two ways an instance runs; the same nested `CLAUDE.md` files serve both.

* **Root + subagents (default for cross-cutting work).** A root instance handles
  anything that crosses module boundaries (e.g. changing a Flow contract in
  `foundation/` that ripples into verifier, orchestrator, experts, delivery) and
  delegates focused, high-volume, or tangential tasks to the shared subagent pool
  in `.claude/agents/`, each in its own isolated context:
  * `security-review` — audits a change against the security invariants (user_id
    scoping, SET LOCAL, sanitization re-entry, identity-set-once, SSRF, locked
    prompts, sandbox gating).
  * `architecture-boundary` — audits import discipline / Flow-only transport /
    one-door-per-layer.
  * `expert-tool-builder` — adds a new expert or tool against the
    self-registration contract.
  * `/invariant-check` — fast grep-based stand-in for the not-yet-built CI
    scope/import gate.
* **Scoped instance (situational).** For deep, self-contained work inside ONE
  module, start an instance in that dir (`cd backend/<module> && claude`) and rely
  on that module's `CLAUDE.md`. Use this only when the work won't cross boundaries.

Each genuine boundary carries its own always-on `CLAUDE.md` (the NEVER-lines and
local conventions, not the architecture): `foundation/`,
`core/{llm,intake,normalizer,verifier,orchestrator,memory}/`,
`security/{sanitizers,filter}/`, `registry/`, `experts/`, `tools/`, `api/`,
`delivery/`. They inherit this file and do not restate the global architecture
(that lives in `docs/`). The frontend owns its own `CLAUDE.md`/`AGENTS.md` — leave it.

## USER VISIBILITY

Always tell the user:

* what you are doing
* why you are doing it
* what assumptions you are making

Do not silently begin implementation.

## REQUIRED READING

Read this before touching any file.

Documentation now lives under `docs/`.

Start at:

`docs/00_START_HERE.md`

This is the mandatory entry point and defines documentation order and
precedence.

The canonical system design is:

`docs/architecture/SYSTEM_ARCHITECTURE.md`

Do not duplicate or redefine system architecture elsewhere.

## EXPERTS AND TOOLS REMINDER

Before implementing new experts or tools:

* Read `docs/architecture/agents/EXPERTS_AND_TOOLS.md`
* Confirm what already exists
* Confirm what is still missing
* Tell the user what you plan to add
* Wait for confirmation when required

## EXPERT → UI CONTRACT

When experts or tools are added or modified:

* Verify whether discovery metadata already contains everything the UI needs.
* Prefer metadata-driven rendering.
* Avoid manual frontend registration when possible.
* The long-term goal is that adding or editing an expert automatically
  updates what the UI can render without requiring frontend changes.

## TOOL VISIBILITY

Whether end users should see tools is a product decision, not an
implementation assumption.

If work touches tool visibility:

* explain tradeoffs
* present options
* do not silently choose a policy

## NOTICE CLEANUP

After all planned experts and tools have been successfully implemented,
verified, and documented, remove obsolete reminder notices from this file.
