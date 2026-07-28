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
6. **REPLACEABILITY — every dependency behind ONE swappable door.** A framework/library/architecture
   is imported in exactly one module, reached elsewhere through a `foundation/contracts/` port, so it
   can be swapped — to another library, architecture, or **language** — by editing one folder. And a
   boundary must **own its guarantees**: if an invariant (spend ceiling, loop cap, fail-closed gate) is
   enforced only by the dependency, we outsourced a promise, not isolated a dependency. Declining a
   rewrite must mean "wouldn't improve it," never "too risky to try."
7. **PROVE IT — tests first-class, verification honest.** Every behavior proven by a test (incl.
   the failure path); **suite green before every commit + verify green before every push**; tests
   and benchmarks NEVER fake a pass (report PARTIAL/NOT-YET truthfully).

Before every commit, run the seven self-checks in `LAW/README.md`. If an answer is "no," fix it or
flag it — never land-and-hope.

## 🦀 RUST — V1 ships in Python; Rust is an experiment on code that already works

**New work is written in Python.** Including new infrastructure. V1 is not done and
has never faced a user; a second toolchain per new component is a tax we don't pay yet.

**Modularity is non-negotiable regardless (LAW 6).** Every dependency behind one door,
every subsystem behind a `foundation/contracts/` port — so any part *could* be swapped
for another language. The point is being **able** to, not doing it.

**Rust experiments target already-built, working components only** — written 1:1
alongside the Python, which stays live. Parallel implementation *requires* an existing
implementation to validate against, which is exactly why new code is the wrong target.
Process: **`docs/architecture/RUST_MIGRATION_STRATEGY.md`** (canonical).

**Nothing is Rust yet.** Owner settled the boundary discussion on 2026-07-28:
stateful/system components default to a separate supervised process with a
versioned API; FFI is reserved for bounded pure computation where profiling
justifies it. Track B is deferred while Python V1 advances. First candidate
remains the Redis budget broker. `foundation/` is LAST (209 in-process
importers). Revisit "new code in Rust" after V1 ships.

If a new component genuinely needs Rust-level guarantees Python can't give, that's a
**proposal with a specific argument** — never a default.

## 📍 KEEP STATUS CURRENT — you own the roadmap's accuracy (standing rule, 2026-07-27)

**`docs/ROADMAP.md` is the single "what should I work on?" entry point.** Read it at
session start. It points at the detailed plans; it also records which of them are stale.

**When you finish anything that changes where we stand, update the status in the SAME
commit as the work.** Not later, not in a sweep — a status doc that lags the code is
worse than none, because agents follow it and work on things already done.

Specifically, before you commit:
- Did this close or advance a benchmark? → update its verdict in
  `docs/benchmarks/V1_GAP_ANALYSIS.md` **and** the mission phase file's `STATUS:`
  line + checkboxes (`docs/benchmarks/mission/PHASE_*.md`). A finished phase moves to
  `docs/benchmarks/reached/` with its outcome recorded inside.
- Did this change what anyone should work on next? → update `docs/ROADMAP.md`
  (§2 open work, §4 lanes, §5 owner-gated).
- Did this make a doc wrong? → fix it or list it in ROADMAP §6 as known-stale. Never
  leave it silently wrong.

**Verdicts are honest or they are worthless.** Report PARTIAL/NOT-YET truthfully
(LAW 7); never mark something done because the work "should" have finished it. If you
cannot verify a claim, say so and leave the status unchanged.

This is the coordinator's job specifically — specialists report their own work, but
keeping the cross-cutting picture true is yours.

## 🚚 "THAT'S X'S JOB" IS NOT A STOPPING POINT — DISPATCH IT (owner instruction, 2026-07-28)

**Finding work that belongs to another tree is the START of the task, not the
end of it.** Writing a proposal and stopping leaves the work undone until that
specialist happens to wake up and read their inbox — which, under pull-not-push,
may be never. The owner's words: *"just run the api specialist and get the task
done ... instead of saying it's the x specialist's job and quitting."*

So when you hit something outside your tree:

1. **Write the proposal anyway** — it is the durable record and the specialist's
   session needs it when they next run.
2. **Then dispatch a worker to do it** — `./scripts/crew.sh run <role> --brief
   <file>`, scoped with `--dir` to exactly the paths it may touch.
3. **Review the diff, run the suite, commit and push it yourself.** You are the
   sole pusher and the integration authority; the worker never commits.

Choosing the shape (`docs/architecture/CREW_WORKFLOW.md` §4.4):
- **headless (`run`)** — bounded task, brief fully specifies it, no judgement
  call the owner or a specialist must make. This is the default.
- **interactive (`start`)** — the work needs a real back-and-forth, or it is the
  owner's to drive.
- **leave it to the specialist's own session** — ONLY when the task genuinely
  needs the context that session is holding, and it is actually running.

**A brief must let the worker disagree.** Tell it to verify the premise first
and to change nothing if the premise is false. A worker that "fixes" a doc to
match a claim that was wrong has made things worse than leaving it alone.

You are the coordinator: your job is that the work gets done, not that it gets
correctly assigned.

## 💭 OWNER'S THINKING — `drafts/owner_thoughts/` (standing rule, 2026-07-27)

**Whenever the owner talks about what they think, believe, prefer, or are
considering — check `drafts/owner_thoughts/` before responding.**

```
drafts/owner_thoughts/active/      live thinking — read ALL of it
drafts/owner_thoughts/references/  supporting depth for the active items
drafts/owner_thoughts/archive/     settled/superseded — read only if cited
```

Triggers: "what I think", "my opinion", "I've been considering", "I feel like",
"personal opinion", or any message that reads as direction-setting rather than a
task. When in doubt, look — it is one `ls`.

These are **opinions, not instructions.** The owner writes them expecting to be
disagreed with ("you are fully allowed to not agree"). Treat them as input to a
decision you still owe them an honest judgement on — see the next section. A
thought file is the start of a discussion, never a work order.

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

**`reports/` layout (tidied 2026-07-28, owner instruction).** One folder per
role, so a report is findable by who wrote it:

```
reports/backend/        the coordinator's own report_vN.md  ← YOURS
reports/{api,memory,orchestration,security,frontend,release}/
```

Only shared information belongs at `reports/` root:
`INTEGRATION_CONTRACT.md` is the tracked backend↔frontend contract. Reports are
information-only; no report name or location implies a reply.

**Owner decisions live in `proposals/to-owner/`, one decision per proposal.**
Use standard proposal headers (`From`, `To`, `Status`, `Priority`, `Summary`)
and an authority-level body: context, exact decision, options/consequences,
recommendation, and what the ruling unblocks.

Before writing one, ask: **can I resolve this myself — by doing work or making
an allowed judgement?** If yes, use ROADMAP, comms, or your report. Only genuine
"blocked on you" work enters `proposals/to-owner/`.

Two failure modes, both of which had happened by 2026-07-28:
- **Padding.** The docket carried tracking notes and resolved history under a
  `NEEDS YOUR DECISION NOW` heading; two of its three "decisions" said in their
  own text that no answer was required. Padding a decision file is not harmless
  — it buries the real items and trains the owner to skim.
- **Omission.** The decisions that actually gated work (the Rust discussion, the
  batch greenlight, whether V1 ships to users) were not in it at all. A docket
  that is missing the live items is worse than no docket.

So: **keep owner proposals current like status.** When settled, append
`## Response`, flip `Status`, move to `proposals/archive/to-owner/`, and record
lasting outcome in canonical docs. New gate gets a proposal same day.
Cross-check ROADMAP §5; both must agree.

**Write your reports to `reports/backend/report_vN.md`** — one NEW file per
finished piece of work, never appended to an old one.

> There is a separate instance for the frontend so if you are not specifically
> assigned to work on the frontend, NEVER make any changes on it.

> Important: YOU must be careful to not let any merge conflicts happen or,
> Overwrite the work of the frontend agent !!

## OWNER PROPOSAL CHANNEL

When owner ruling is required, write one proposal under
`proposals/to-owner/`; never ask through reports. Tell owner inbox is ready in
one line. Owner may reply inside proposal or through `proposals/to-backend/`;
backend coordinator records outcome and archives proposal.

## ACTIVE MISSION (multi-session — check at session start)

A long-running backend mission is in progress: **Premium-Parity + V1 Capability
Pass**. Its durable, resumable map is `docs/benchmarks/mission/README.md` — read
it (and `docs/benchmarks/V1_GAP_ANALYSIS.md` for the priority order) at the start
of any session that continues this work. Phase files live in
`docs/benchmarks/mission/`; a phase moved to `docs/benchmarks/reached/` is done
(outcome recorded inside).

**Two owner briefs feed it** (raw text local + gitignored, kept as settled
source in `proposals/archive/to-owner/`; committed docs below are canonical):
- `BACKEND_PARITY.md` → settled as the phase map + `V1_GAP_ANALYSIS.md`.
- `BATCH_ARCHITECTURE.md` → settled as `docs/architecture/BATCH_ARCHITECTURE.md`
  (`[PROPOSED]` — a batch layer between orchestrator and experts; the structural
  frame for the graph-blocked benchmarks; propose-first + stability-first, nothing
  built).

Priority order lives in **`docs/ROADMAP.md` §2** — not here, so it cannot rot in
two places. (The old `CB5 → CB1 → CB4 → CB6` chain is retired: CB6 PASSES, and
CB4's mirror + CB5's seal shipped.) **Standing rule — Prime Directive:**
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
