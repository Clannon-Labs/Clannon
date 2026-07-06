# Mission Engine — handoff (end of session, 2026-07-05)

Owner is closing up for the night. This is the resume point for the Mission
Engine build — read this first, before re-deriving state from scratch.

## Update (2026-07-06 session, continued) — §6 operate-step BUILT + committed

`members()` landed on the Protocol (`85b4f15`); backend also ruled the
conclude-path question (poll, not push — matches my recommendation, full
ruling in `proposals/archive/to-backend/2026-07-06_conclude-path-signal-design.md`).
Both resume conditions from the note below are now satisfied.

**Built `core/orchestrator/mission_operate.py`** (§6 + the conclude-path):
`create_mission`, `read_mission_state`, `apply_turn`, `write_mission_status`,
`needs_approval` (§7 autonomy gate), `run_operate_step` (the full per-turn
sequence), `conclude_mission`. Two real bugs caught by reading the actual
implementer rather than trusting my own design doc's assumptions, before any
code was written against them:

1. `GraphPort.lookup()` is hard-restricted to `NodeLabel.CODE_FILE`
   (`core/memory/graph_manager.py:104`) — a bare `label=MISSION` there is
   ALWAYS empty, not just when missing. Fixed: `read_mission_state` reads a
   MISSION the same way as tasks, via `members(scope, MISSION)` filtered
   client-side on the `mission_id` property.
2. **Node ids are never caller-supplied.** `write()`'s implementer computes
   its own id from `scope` + a natural-key property, discarding whatever
   `node_id` a caller sets on the `GraphNode` passed in (verified directly,
   not assumed). An advisor review caught the trap in my first draft: I was
   about to replicate the implementer's internal `user|repo|key` id format in
   orchestrator code to build edges, which would (a) couple this module to
   an undocumented format `GraphNode.node_id`'s own docstring says is opaque,
   and (b) make my own hermetic test-double share that same assumption,
   turning the test into a circular oracle that couldn't catch a real
   mismatch. Fixed: `apply_turn` writes nodes first, then a SECOND pass reads
   back their real, port-assigned ids via `members()` before writing
   BLOCKS/FEEDS/SUPERSEDES edges. This means the module depends only on "the
   port hands me ids I reuse" — true for any conforming `GraphPort`, fake or
   real, so nothing here is coupled to Kuzu specifically.

Also caught, same way: `success_criteria` is a native Kuzu `STRING[]` (plain
descriptions), not a list of dicts — `core/memory/graph_store.py:172`
confirms this directly.

**Verification (`tests/mission_operate.py`, 14 tests, all green):** create+read
round trip, §1 create-only anchor survives a repeat write, apply_turn's
two-pass node-then-edge write (proves edges reference harvested ids, not the
bare task_id strings), SUPERSEDES as an ASSERTED edge immune to a later
downgrade, §7 budget pre-check pauses BEFORE any task content is written
(not just a status check), §7 autonomy gate escalates above the
autonomous-safe set, §4 completion gate both holds (unmet criterion) and
concludes (all met), a no-op on an already-concluded mission, §9 restart
survival (discard all Python state, reconstruct purely from the durable
store, assert the anchor + a superseded-but-present task survive
byte-for-byte), tenant isolation, and — the capstone — one test driving the
REAL `core.memory.graph_manager.GraphManager` end-to-end (not just the
hermetic fake), proving the node-id-harvest approach actually works against
the real backing store. §9 step 2 (mid-run compaction) is honestly out of
scope for this module: it acts on the orchestrator's working context, which
this module doesn't have (pure graph read/write) — it lands with whatever
wires this operate-step into the live turn loop.

**Not done / explicitly deferred, not forgotten:**
- **Wiring into `core/orchestrator/loop.py`** — this module is built and
  verified but not yet called from the live turn loop. Per the Prime
  Directive, this module + its tests are the gate the batch orchestrator
  crosses before that wiring lands, not a shortcut past it. `run_operate_step`
  is the entry point once that wiring is designed.
- **§7's `awaiting_approval` -> back to `active`** (the user-approves-and-resumes
  path) isn't built — `needs_approval` only handles the forward escalation;
  nothing yet clears it. Flagging so it isn't assumed done.
- Full suite green throughout (993 passed, 6 env-skips, verified in isolation
  from an unrelated, uncommitted, in-progress collection error in
  `backend/api/run_driver.py` — another agent's mid-edit config-centralization
  work, not touched by or related to this build).

## Update (2026-07-06 session, earlier)

Re-checked the blocker fresh rather than trusting the paragraph below verbatim:
`foundation/contracts/graph.py` still has no `def members` on `GraphPort` as of
this session (grepped directly). Nothing else changed — no new commits since
`73453ea`, working tree clean, inbox (`proposals/to-orchestration/`) empty. Per
this doc's own instruction ("a nudge to backend, not new design or waiting on
memory"), filed `proposals/to-backend/2026-07-06_members-protocol-nudge.md`
(high priority, exact copy-paste signature from the already-built
`GraphManager.members()`, `core/memory/graph_manager.py:214`).

Used the wait per charter ("design around the gap until answered") rather than
idling: handoff step 3 below flags the conclude-path signal mechanism
(push vs. poll, for memory's `clear_mission`) as genuinely unresolved by the v2
ratification — that decision doesn't depend on `members()` landing, so filed it
now as `proposals/to-backend/2026-07-06_conclude-path-signal-design.md`,
recommending **poll** (self-checked by `BatchAwarenessPort`'s own implementer,
which already has same-tree access to `GraphManager` — zero new cross-layer
contract, and self-healing against a missed signal, unlike push which needs a
new `MemoryPort` method and has no retry if the notification is lost).

Nothing else was unblocked to build this session — confirmed the charter's
other frontier items (entropy routing #64, both charter tools, round-2
stability audit) are all already done per `reports/orchestration/report_v1.md`.
Next resume: check whether `members()` landed AND whether backend ruled on the
conclude-path signal; if both, step 2 below (the §6 operate-step) and step 3
(conclude-path) can build in one pass instead of two round-trips.

## Ratified design

`proposals/archive/to-orchestration/2026-07-05_mission-engine-v2-ratified.md`
— backend's ruling on my design proposal
(`proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md`).
Approved in full: the GraphPort reframe (generic `NodeLabel`/`EdgeLabel`
values, not bespoke foundation types), the durable/ephemeral partition (§1),
gated evidence-checked completion (§4), the additive operate-step (§6),
autonomy boundaries (§7), the compaction split (§8), and the verification plan
(§9). Read the ratification before the original design doc — it's shorter and
has the actual rulings; go to the design doc only for the full reasoning
behind a specific section.

## What's built + committed

**`core/orchestrator/mission.py`** (commit `876943f`) — the half of the design
that doesn't touch `GraphPort`:
- `MissionStatus` — the full §3 lifecycle enum: `active`, `blocked`,
  `proposed_complete`, `done`, `failed`, `user_ended`, `budget_paused`,
  `awaiting_approval`.
- `Criterion`, `TaskOutcome`, `CriterionVerdict`, `CompletionJudgment` — the
  shapes the completion gate operates on. `TaskOutcome` is deliberately a
  *projected* type, not a raw `GraphNode` — kept valid regardless of how the
  graph seam resolved (see below; it has resolved, cleanly, to the shape this
  file already assumed).
- `evaluate_completion()` — the §4 fail-closed gate for
  `proposed_complete -> done`. Correlates verdicts to criteria by *position*,
  then checks the claimed `description` at that position as an integrity
  check on the correlation (catches a judgment that reordered or dropped a
  criterion). Any length mismatch, description mismatch, or unmet criterion
  holds at `PROPOSED_COMPLETE` — never auto-advances on an incomplete or
  malformed judgment.
- `budget_is_sufficient()` — the §7 mission-level budget pre-check, consuming
  `foundation.TokenBudget` exactly as shipped. No budget design owed — this
  goes live once backend's Redis-backed `BudgetPort` impl lands (separate,
  unrelated to this handoff's blocker).

**`tests/mission_engine.py`** — 11 tests (the completion-gate matrix: all-met,
one-unmet, verdict-count-mismatch both directions, reordered-verdicts,
paraphrased-description, the vacuous zero-criteria case; the budget matrix:
both ceilings sufficient, mission ceiling too low, user ceiling too low, no
mission ceiling set). Suite was green (1026 passed, 6 env-skips) at commit
time.

**Not built yet:** the operate-step itself (§6 — the per-turn read/write
against `GraphPort`) and the conclude-path (§4's terminal transition, which is
also the signal source backend wants exposed for memory's `clear_mission`
hook — see the ratification's cross-dep #1). That's next, once unblocked.

## Exactly what unblocks it, and what I found already resolved

Checked `foundation/contracts/graph.py` fresh rather than trusting the
ratification's phrasing verbatim (it's already committed, own tree, so this is
current — not a stale assumption). **Both seam questions from my design are
already answered in the committed contract, not just routed:**

1. **§1 node-mutation semantics — RESOLVED: Variant A.**
   `GraphPort.write()`'s docstring: *"A NODE's properties mutate IN PLACE on a
   repeat write to the same `node_id` (verified against Kuzu's `MERGE ... ON
   MATCH SET` — the Mission Engine relies on this for a TASK's mutable
   `status`; no transition history is kept, by design)."* This is my preferred
   variant and exactly what `mission.py`'s design already assumes — no rework
   needed there.
2. **§2 mission-scoped bulk read — RESOLVED (shape pinned, method not yet
   landed).** The `NodeLabel.MISSION`/`TASK` comment: *"mission_id lives as a
   node PROPERTY (a filter under user_id), not a `GraphScope` dimension — read
   via `members(scope, TASK, parent_id=mission_id)`."* `lookup()`'s own
   docstring confirms `members()` is a **new Protocol method, added together
   with its `GraphManager` implementer** — i.e. specified, not yet present on
   `GraphPort` itself.

**Update — checked again after first writing this section, because memory
committed while I was writing: the picture narrowed further, so trust this
paragraph over the timeline above.** Memory's build landed and committed
(`4d521d2`, their own handoff is `core/memory/HANDOFF_*.md` if it still
exists tomorrow — read it, it's precise). Confirmed directly (not assumed):
`core/memory/graph_manager.py:214` has a real, committed `members(scope,
label, *, parent_id="")` implementation, empirically tested against Kuzu's
`MERGE ... ON MATCH SET` for the mutation question too. **Memory's side is
fully done.**

**The actual remaining blocker, precisely, is narrower than "memory is
building it": `GraphPort.members()` is deliberately NOT yet added to the
Protocol in `foundation/contracts/graph.py`.** Confirmed by grep — no
`def members` there as of this handoff. Memory's own handoff doc says this
was the backend-agent's specified sequencing on purpose: `GraphManager`
gets the method first (so it stays a strict superset of `GraphPort`,
keeping every `isinstance(manager, GraphPort)` check green throughout),
*then* the backend-agent adds the matching method to the Protocol. That
second step is backend's, not memory's and not mine — nothing to chase from
either of us, just something to check for on resume.

**So on resume: don't re-ask the two seam questions (both answered,
memory's side fully built+committed+tested) — check ONE thing:** does
`foundation/contracts/graph.py` now declare `async def members(...)` on
`GraphPort` alongside `depends_on`/`lookup`/`write`? If yes, build against
it. If not yet, the block is purely "backend hasn't landed their one-method
Protocol addition yet" — a nudge to backend, not new design or waiting on
memory.

## Next steps once `members()` lands

1. Confirm `GraphPort.members()`'s Protocol signature matches the already-built,
   already-tested `GraphManager.members(scope, label, *, parent_id="") ->
   GraphResult` (`core/memory/graph_manager.py:214`) — if it drifted, that's
   worth a quick note back to backend, not a silent adaptation.
2. Build the §6 operate-step in `core/orchestrator/` (new file or extend
   `mission.py` if it stays small — check line count, aim ~300, split if not):
   read `intent`/`success_criteria` + task set via `members()`, the §7
   budget pre-check via `budget_is_sufficient()` (already built), advance/
   propose via `write()` (node-mutation now confirmed safe), completion check
   via `evaluate_completion()` (already built) once all tasks are terminal.
3. Build the conclude-path as the *single* place a mission reaches `done` /
   `failed` / `user_ended` — per my response on the ratification, this is
   the one clean transition point memory's `clear_mission(user_id, mission_id)`
   hooks off. Pin down push-vs-poll with backend/memory before wiring this
   specific part (flagged as genuinely ambiguous, not yet resolved — the
   ratification says "expose it" but doesn't say whether that means an
   explicit signal or memory polling terminal `MISSION` node status).
4. Write the §9 verification suite: hermetic restart + mid-run compaction
   simulation against a fake `GraphPort`, per the design doc's acceptance
   criteria. This is the gate before the batch orchestrator goes on top of
   any of this — do not skip or shortcut it under time pressure.
5. Suite green, explicit-pathspec commit, report to
   `reports/orchestration/report_v1.md`, notify backend.

## State at handoff

- My tree (`core/orchestrator/`, `registry/`, `experts/`, `tools/`): clean,
  nothing uncommitted. `876943f` is the last commit; no WIP to save.
- Both charter-listed independent tools (`tools/chart.py`, `tools/diff.py`)
  already exist — no other unblocked backlog item was left on the table
  before stopping.
- Batch orchestrator + budget-wiring (my other two owner-assigned pieces)
  remain correctly sequenced after this — not started, not blocked on
  anything new beyond what's already known (batch orchestrator waits on this
  engine's §9 verification; budget-wiring waits on backend's Redis impl).
