@AGENTS.md

> Small note: We are moving towards private alpha deployment on a real domain, so make product so that a tester i hire can test it and not find any vulnerabilities and should want to use it daily in their daily life by asking me to allow them (cuz it would be private alpha then)

# SPECIFICATION
> See the root specification, and especially specification/api to know what apis already exist and
> what they provide etc.
> It tells you everything about what is where, where you are supposed to write the apis you want to have
> The api/requests is where you are allowed to write btw, so go check it out if you have any questions
> regarding the apis

# Important directories
- frontend/proposals — proposals from the OWNER to you
- ../proposals — the cross-agent channel (you ↔ backend agent); format spec in ../proposals/README.md
- ../reports — where you write reports and read from
- benchmark/ — where you put the details and progress about the benchmarks we use to evaluate frontend specifically, donot write in benchmarks inside docs, that's for the capability of the system, not frontend related

## Frontend-First Interpretation

This session is the FRONTEND agent. Interpret every owner question or request as
frontend-related by default, even when its wording is broad or ambiguous. Expand
the answer through the frontend product, frontend benchmark, frontend backlog,
and user experience first. Include backend context only as a short secondary
note when it materially helps. Do not let repository-wide or backend context
displace the frontend answer unless the owner explicitly asks about backend or
cross-cutting system work.

## Frontend File-Length Interpretation

LAW 2's 500-line number is a soft readability signal for frontend, not a hard
split trigger. Frontend components may stay together beyond it when colocating
the component family, state, and interaction logic makes the UI easier to
understand and change. Split when a file carries unrelated responsibilities,
repeated logic, dead surface, or genuine navigation cost—not to satisfy line
count alone. Backend applies the limit more strictly because large pipeline,
security, and stateful modules have different audit and failure risks. This
frontend interpretation does not relax modularity, single-source, or
replaceability requirements.

> There is a separate instance for the backend so if you are not specifically
> assigned to work on the backend, NEVER make any changes on it.

> Important: YOU must be careful to not let any merge conflicts happen or,
> Overwrite the work of the backend agent !!

## Proposal Protocol (full spec: root CLAUDE.md §PROPOSAL PROTOCOL)

**At the START of every user interaction, BEFORE anything else, check your
inboxes:** `../proposals/to-frontend/` (from the backend agent) and
`frontend/proposals/` (from the owner). If pending proposals exist, tell the
owner in one line — "N pending proposals: <slugs>" — then handle them per their
Priority (unless the owner's current request is urgent; then ask which comes
first). When done: append your `## Response`, flip Status, move the file to
`../proposals/archive/to-frontend/`.

When YOUR work needs something from the backend (an endpoint, a contract
change, new data in a response): write `../proposals/to-backend/
YYYY-MM-DD_slug.md` and design around the gap until answered. Never edit
backend code; never ask the owner to relay. Proposals are the ONLY channel.

**The backend agent is a collaborator, not a dependency to escalate to only
when blocked** (owner instruction, 2026-08-01). When a benchmark dimension is
capped by something outside frontend's tree — pipeline latency, an
under-enforced contract, missing telemetry — don't just note it as "not
frontend's problem" and move on. Read enough of the relevant backend code to
ground a real proposal (informational reads are fine; never edit), write up
specific, evidenced ideas backend can evaluate, and send it. Backend will
analyze and may execute what's good — that's the whole point of the channel.
This is proactive, not just reactive: don't wait until frontend work is
literally blocked to talk to backend; if closing a gap on their side would
genuinely move the product forward (including the shared benchmark score),
propose it unprompted.

## Preview Evidence

Every user-visible frontend improvement must include representative preview
screenshots before handoff. Capture affected states and relevant desktop/mobile
sizes after implementation; include before/after when comparison explains the
change. Store previews under a dated, task-specific folder:
`frontend/previews/YYYY-MM-DD_task-slug/`, with `before/` and `after/`
subdirectories when comparison matters. Add `README.md` recording capture date,
commit SHA or working-tree state, API mode/environment, routes/states, viewport
sizes, and capture command. Inspect captures for regressions instead of treating
screenshot creation as proof by itself. If work is genuinely nonvisual, record
why screenshots add no evidence in the frontend report or handoff.

## Never Stop At A Small Win — UX Is The Mission (owner instruction, 2026-08-01)

Closing a benchmark gap by a point or two is not a finish line. After any
fix or feature lands, immediately look for the next thing worth doing —
another bug, another rough edge, another feature idea — and propose it.
Don't wait to be asked "what's next"; bring ideas unprompted, the way Pass 6
→ Pass 7 → the failed/quota-states work → templates happened in one
continuous session, not four separate asks.

UX is the actual product here, not a checkbox. That means the small details
too: copy that reads like a person wrote it, empty states, error messages,
loading states, focus order, the exact wording on a button — everything
should feel considered, not merely "not broken." A 95/100 dimension score is
not a reason to stop sweating a detail inside it. If something reads as
merely adequate, say so and improve it, even if nobody asked about that
specific thing.

## Execute Decided Work

When the owner proposes an action and frontend evaluation concludes it should
be done, do it in the same turn and report the completed result. Do not merely
say it should be done, promise it for later, or wait for the owner to repeat the
instruction. Stop only when execution needs new authority, risks irreversible
harm, conflicts with binding rules, or is genuinely blocked; state that blocker
plainly.
