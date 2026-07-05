# Mission Engine — handoff (end of session, 2026-07-05)

Owner is closing up for the night. This is the resume point for the Mission
Engine build — read this first, before re-deriving state from scratch.

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

**The actual remaining blocker, precisely:** `git status` (checked at
handoff time) shows memory mid-flight, uncommitted, on exactly this —
`core/memory/graph_manager.py` (modified), `core/memory/graph_store.py`
(modified), `core/memory/mission_graph_store.py` (new),
`tests/memory_mission_graph.py` (new). This is memory's tree, not mine — not
touched, not read beyond `git status`. Memory is saving its own state
tonight too, per backend.

**So: don't re-ask the two seam questions on resume — they're answered.**
The only thing to check on resume is whether `GraphPort.members()` has
landed on the Protocol (i.e. `foundation/contracts/graph.py` has a `members`
method alongside `depends_on`/`lookup`/`write`) and whether
`GraphManager.members()` is implemented + committed.

## Next steps once `members()` lands

1. Confirm the landed signature matches `members(scope, label, parent_id=...) -> GraphResult` (the comment-pinned shape) — if it drifted, that's worth a quick note back to memory/backend, not a silent adaptation.
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
