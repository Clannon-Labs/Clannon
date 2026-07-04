# CLAUDE.md — Clannon (production monorepo)

## ROOT MANAGER ROLE

This CLAUDE.md belongs to the repository root and is intended for the
ROOT MANAGER agent.

> conversation(s)/ was changed to reports/

> There is a separate instance for the frontend so if you are not specifically
> assigned to work on the frontend, NEVER make any changes on it.

> Important: YOU must be careful to not let any merge conflicts happen or,
> Overwrite the work of the frontend agent !!

## PROPOSAL PROTOCOL (cross-agent channel — no owner relay)

Two interactive sessions work this repo: the BACKEND agent (this file's reader,
root + backend/) and the FRONTEND agent (frontend/). They exchange work through
proposal FILES — never by editing the other side's code, never by asking the
owner to carry a message. Format spec + worked example: `proposals/README.md`
(filename `YYYY-MM-DD_slug.md`; header From/To/Status/Priority/Summary + an
optional `Wake:` line; body with contract + acceptance criteria; receiver
appends `## Response`, flips Status, archives).

**At the START of every user interaction, BEFORE anything else, check your
inbox:**

- Backend agent: `proposals/to-backend/` (from the frontend agent) and
  `backend/proposals/` (from the owner).
- Frontend agent: `proposals/to-frontend/` and `frontend/proposals/`.

If pending proposals exist: tell the owner in one line — "N pending proposals:
<slugs>" — then handle them (accept / reject / act, per their Priority and your
CONTEXT.md rules) unless the owner's current request is urgent, in which case
ask which comes first. Never leave a proposal pending that you could have
handled; when done, append your `## Response`, flip Status, and move the file
to `proposals/archive/<your-inbox-name>/`.

When YOUR work needs something from the OTHER side (an API change, a contract,
a new endpoint, UI for a backend feature): write a proposal file into the other
agent's inbox (`proposals/to-frontend/` or `proposals/to-backend/`), note it in
your report, and design around the gap until answered. Do NOT relay through the
owner. Proposals are the ONLY cross-agent channel.

**Auto-wake:** writing to an inbox automatically types a message into the target
agent's tmux session (`clannon-backend` / `clannon-frontend`; see
`proposals/README.md` §Wake System). **You choose the message:** put a one-line
`Wake:` header in the proposal and that exact line is typed (as `[auto-wake]
<your line>`) — ping the other agent in your own words about what you need or
what changed. Omit `Wake:` for the generic "New proposal in your inbox" default.
If you receive an `[auto-wake]` message, treat it EXACTLY like the owner saying
"check your inbox": run the inbox check above and handle what you find. Don't
wait for a wake to check — the start-of-interaction check still applies (the
wake only covers you being idle).

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
