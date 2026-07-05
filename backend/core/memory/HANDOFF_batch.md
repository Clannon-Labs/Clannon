# Handoff — Mission Engine graph substrate (batch phase)

Written 2026-07-05, end of session. Owner closed the laptop for the night.
This file is for tomorrow's `clannon-memory` session to resume from — read
it first, before checking proposal inboxes.

## Where things stand: committed, not just WIP

Everything described below is **already committed** (`4d521d2` on `main`,
suite green: 1045 passed, 6 env-skips) — this is a status/next-steps
handoff, not a "resume unfinished code" one. **Not yet pushed** — the
backend-agent said they'd push; confirm that happened before assuming it's
on the remote.

## What landed in `4d521d2`

Ratified answers to orchestration's two GraphPort-semantics questions
(`proposals/archive/to-backend/2026-07-05_graphport-semantics-answers.md`,
ruling in `proposals/archive/to-memory/2026-07-05_graphport-rulings-mission-engine.md`):

- **Q1 — in-place node-property mutation.** `MERGE ... ON MATCH SET` on a
  repeat write to the same node id genuinely mutates properties in place —
  proven empirically (a disposable-Kuzu script, then a proper test). No
  transition history is kept: a TASK's `status` is a mutable cursor,
  `SUPERSEDES` carries re-plan history (a different concept), not status
  churn.
- **Q2 — `mission_id` as a node property, not a `GraphScope` dimension** (the
  backend-agent's ruling, not my original lean — I'd proposed this as one
  option and they ratified it, reasoning `mission_id` is a filter *within* a
  user's own graph, not a tenant boundary, so it shouldn't muddy
  `GraphScope` the way a second optional dimension would).

### Files
- **`foundation/contracts/graph.py`** — NOT mine; the backend-agent already
  placed `NodeLabel.MISSION/TASK`, `EdgeLabel.BLOCKS/FEEDS/SUPERSEDES`, and
  tightened the `write()`/`lookup()` docstrings, in `b0e206f` (pushed before
  my build started). Nothing to do here.
- **`core/memory/graph_store.py`** — added the `Mission`/`Task` node tables +
  `Blocks`/`Feeds`/`Supersedes` rel tables to `_ensure_schema` (via a new
  `_create_if_absent` helper, replacing the old copy-pasted try/except
  pairs — CodeFile/IMPORTS use it too now, no behavior change). `
  GraphReadResult` gained a `rows: tuple[dict, ...]` field for typed bulk
  reads (`paths` is still the CODE_FILE traversal shape; the two are never
  populated at once). Added `connection()` — a thin public wrapper around
  the existing `_kuzu()` — so the new sibling module below can reuse the
  SAME embedded Kuzu handle. **442 lines** (was 397; stayed well under the
  LAW-2 500-line ceiling because the bulk of the new logic moved to a
  sibling file — see next).
- **`core/memory/mission_graph_store.py`** (NEW, 182 lines) — everything
  Mission/Task-specific: a `_TypedNodeSchema` dataclass (`create_only` vs
  `mutable` column tuples) + a `_TYPED_NODE_SCHEMAS` dict keyed by
  `"mission"`/`"task"` (== `NodeLabel.MISSION.value`/`NodeLabel.TASK.value`,
  no separate mapping needed), `upsert_typed_nodes()` (generic MERGE-by-id,
  `ON CREATE` sets everything, `ON MATCH` sets only `mutable` — the Q1
  mechanism, generalized off CodeFile's one-hardcoded-property version),
  `upsert_typed_edges()` (generic MERGE-by-connectivity, mirrors
  `upsert_edges`' asserted-always-wins protection), `typed_members()` (the
  Q2 bulk filter-read: `WHERE user_id = ... AND repo_id = ... [AND
  mission_id = parent_id]`), and `is_known_kind()` (a small public check so
  `graph_manager.py` doesn't reach into this module's private schema dict).
  **Why a separate file, not added to `graph_store.py`:** adding it inline
  first pushed `graph_store.py` to 573 lines, over the LAW-2 ceiling — moved
  it out once that was measured, not guessed at upfront.
- **`core/memory/graph_manager.py`** (266 lines, was ~199) —
  `write()`'s node/edge loops now dispatch three ways: CODE_FILE (untouched,
  original code path), MISSION/TASK (new, generic, via
  `mission_graph_store.upsert_typed_nodes`), anything else (still honestly
  rejected with a note, unchanged). **Security-relevant detail:** the typed
  node row is built as `{**n.properties, "id": ..., "user_id": ...,
  "repo_id": ...}` — properties spread **first**, authoritative fields set
  **after** — so a caller can never clobber its own row's storage identity
  by naming `id`/`user_id`/`repo_id` inside `properties`. Verified this
  specific protection red-then-green (temporarily reversed the spread
  order, confirmed the test fails, reverted) before trusting it. Also added
  **`members(scope, label, *, parent_id="")`** — the new bulk-read method.
  **Deliberately NOT yet on the `GraphPort` Protocol** — this is the
  coordination sequencing the backend-agent specified: `GraphManager` gets
  it first (becomes a superset of the Protocol, so
  `isinstance(manager, GraphPort)` stays green throughout), then the
  backend-agent adds it to the Protocol in `foundation/contracts/graph.py`
  once told it's landed. **That "tell them" step is the next action** — see
  below.
- **`tests/memory_mission_graph.py`** (NEW, 19 tests, all passing) — Q1
  in-place mutation + create-only-field immunity (a MISSION's
  `intent`/`success_criteria` survive a repeat write unchanged, only
  `status`/`updated_at` refresh), tenant isolation (same `mission_id`/
  `task_id` under two different `user_id`s never cross-leak), `parent_id`
  filtering, asserted-edge protection on BLOCKS/FEEDS/SUPERSEDES, degrade-
  never-fail, the clobber-protection fix (RED-then-GREEN verified), a mixed
  CodeFile+Mission/Task `write()` call, and the `isinstance` superset check
  itself as an explicit test.

## What's genuinely NOT done yet (the real next steps)

1. **Tell the backend-agent `members()` has landed** (this file mentioning
   it doesn't count — write a proposal to `proposals/to-backend/` first
   thing tomorrow, or check if they've already noticed via the commit and
   responded). Once told, they add `members()` to the `GraphPort` Protocol
   in `foundation/contracts/graph.py` (their seam) — that's the one
   remaining piece before orchestration's Mission Engine can actually call
   `members()` through the Protocol type rather than the concrete
   `GraphManager` class directly.
2. **Confirm the push happened.** I committed (`4d521d2`); the owner's
   instruction was "commit it and tell me to push" — that message hasn't
   been sent yet as of writing this file. Send it, or check whether the
   backend-agent already pushed proactively.
3. Nothing else is required for THIS thread to be complete — the Kuzu
   tables, the generic marshalling, and `members()` are all built, tested,
   and committed. Orchestration's actual operate-step (the code that reads/
   writes real Mission/Task data during a running mission) is NOT mine —
   that's gated on them building against this substrate, not something to
   pre-build here.

## Known, deliberately-not-fixed observation (flag, don't chase tomorrow unless asked)

The graph tier (BOTH the pre-existing CodeFile data and this new Mission/
Task data) has **no right-to-erasure wiring** — `manager.py`'s
`delete_user()` only calls `store.delete_user()` (the Qdrant vector tiers),
never anything graph-side. This is a **pre-existing gap**, not introduced by
tonight's work (grep confirms no `graph_store`/`graph_manager` erasure path
existed before either). Structurally identical to the `delete_user` gap
flagged and fixed in the cross-batch awareness design
(`proposals/archive/to-backend/2026-07-05_cross-batch-awareness-memory-design.md`
§6) — same fix shape would apply here (a `delete_user(user_id)` in
`graph_store.py`/`mission_graph_store.py`, wired into `manager.py`'s
existing method). **Not fixed tonight** — out of scope for the Q1/Q2 build
task specifically, and raising it as new scope at the end of a long session
felt like exactly the kind of unrequested addition to avoid. Worth a
proposal if nobody else raises it first.

## Other threads, for context (unrelated to tonight's build, still holding)

- **Cross-batch awareness memory slice** — ratified
  (`2026-07-05_cross-batch-design-ratified.md`, archived), contract slice
  inert until Mission Engine lands. Nothing to build yet.
- **CB2 thin-slice benchmark** — landed and committed earlier this session
  (`947141c`). Done, not part of tonight's work.

## Where to look first tomorrow

1. `proposals/to-memory/` — check for anything new (ratification response,
   a correction, or a new assignment) before assuming this handoff is still
   the latest state.
2. `git log --oneline -5` — confirm `4d521d2` is still `HEAD` and whether
   it's been pushed (`git log origin/main..HEAD` — empty means pushed).
3. If nothing new and the push hasn't happened, that's the very next
   action: tell the backend-agent to push, and/or write the "members()
   landed" proposal from step 1 above if it wasn't already sent before the
   laptop closed.
