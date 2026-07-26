# Mission Engine — handoff (end of session, 2026-07-05)

Owner is closing up for the night. This is the resume point for the Mission
Engine build — read this first, before re-deriving state from scratch.

## BUILT (2026-07-26, later still) — §5 dependency-graph traversal (code.dep_graph)

The nav-patch-tooling arc is now DONE: §2 patch-apply, §3 archive extraction, §4
AST search, §5 dep-graph traversal — all built + proven. New tool `code.dep_graph`
(`tools/dep_graph.py`): BFS over import/include edges (Python import/from, C
#include) extracted via the same tree-sitter parses `code.ast_search` uses,
outward from a starting file — `dependencies` (outgoing), `dependents` (incoming,
who imports this file), or `both`, bounded `max_depth`/node/edge caps, cycle-safe.
Factored the shared tree-sitter parser setup out of `ast_search.py` into new
`tools/_treesitter.py` first (was duplicated infra risk the moment a second
AST-based tool showed up, not just a repeated constant). Three-places checklist +
both pin lists updated again. 14 new tests (`tests/dep_graph.py`), full suite green
(1424 passed; the 10 failures present in the full run were traced individually —
4 pre-existing on a clean tree in `tests/benchmarks/sse_contract_drift.py`, outside
my trees; 6 more pass cleanly in isolation both with and without this change —
order-dependent pollution elsewhere in the suite, not this build). Commit
`908500d`. Full detail: `reports/orchestration/report_v41.md`.

**Also noticed while committing, not acted on:** root `CLAUDE.md` now names a
FIFTH interactive session — a SECURITY specialist (`clannon-security`, owns
`security/**`) — that didn't exist in this file's last read. Doesn't change
anything in my tree; flagging so a future resume doesn't assume the old
four-session topology.

**Resume: check `proposals/to-orchestration/` first.** No known blocker. The
nav/patch-tooling design's full scope (§1-§5) is now built; the honest remaining
gap toward CB2's actual large-repo target is cross-call persistence (a repo
extracted for one `code.engineer` call doesn't survive to the next — flagged
since report_v39, ties to the Mission Engine, no design started). Otherwise next
items are unprioritized: that persistence design, or whatever backend/owner next
pull from `V1_GAP_ANALYSIS.md`.

## BUILT (2026-07-26, later) — §4 AST-aware search (code.ast_search)

Backend actioned the deferred tree-sitter dependency ruling (`f4c6e51`,
`requirements.txt`) and pinged the inbox (`proposals/archive/to-orchestration/
2026-07-26_tree-sitter-dependency-ruling.md`, now archived+responded). Built
`tools/ast_search.py`: `code.ast_search`, one new tool (deterministic, no LLM,
matches `fs.patch`'s decomposition — `code.engineer` gains a sharper
instrument, not a new expert). Python + C via real tree-sitter parses; finds a
symbol's definitions (function/class/struct/union/enum) and plain-name
call-sites. Wired through the three-places checklist (`code.engineer`'s
`tools` tuple, `batches.yaml`'s `engineering.tool_keys`, the two
security-sensitive pin lists in `tests/expert_contract.py` + `tests/
orchestrator_engineering_batch.py`).

An advisor review caught a real bug pre-commit: the `kind` (definition/
reference) filter was applied AFTER the tree walk collected up to the match
cap unfiltered — a file dense with call-sites of a name could fill the cap
before reaching its own (later) definition, silently reporting "not found."
Fixed: `kind` now narrows what the walk itself collects. Also tightened
honesty: a file skipped (unreadable, oversized, or a per-file match-cap hit)
is now counted in a new `files_skipped` field and reflected in `truncated` —
previously that could silently under-report a result as complete when it
wasn't. 14 tests (`tests/ast_search.py`), full suite green. Full detail:
`reports/orchestration/report_v40.md`.

**v1 scope, explicit not silent:** plain-name matches only (`foo(x)`, not
`obj.foo(x)` — the callee there is an `attribute` node, unmatched). Documented
in the tool's own description, not silently claimed as full coverage.

**Resume: §5 dependency-graph traversal next**, per the ratified design's
build order (`proposals/archive/to-backend/2026-07-25_nav-patch-tooling-
design.md` §6) — built ON `code.ast_search`'s parse output (import/include
edges extracted the same structural way symbol definitions are). Not designed
yet; check `proposals/to-orchestration/` first. Also still open, unchanged:
cross-call persistence (an extracted repo doesn't survive past one expert
call — flagged in report_v39, ties to the now-wired Mission Engine, no design
started).

## BUILT (2026-07-26) — §3 archive-into-workspace extraction (CB2 real-repo-input)

Unblocked: `git log` showed security's archive-modality half of `security/
sanitizers/uploads.py` landed (`7bfaddf`) since the last session, closing the
gate this section was waiting on. Built + proven:
`ExpertHandler._seed_inputs`/`_extract_archive` (`registry/capabilities/
handler/experts.py`) now extracts an admitted `archive`-modality `InputFile`
into the workspace member-by-member (byte-verified caps, per-member malware
re-scan, all-or-nothing on any breach) instead of writing the zip as one
opaque blob. Full detail, including two real gaps an advisor review caught
before this was called done (silent rejection on failure; an unbounded prompt
listing for a large repo) and how they were fixed:
`reports/orchestration/report_v39.md`.

**Resume: §4 AST-aware search next**, per the ratified design's build order
(`proposals/archive/to-backend/2026-07-25_nav-patch-tooling-design.md` §6) —
gated on backend's tree-sitter dependency ruling (approved in principle in
the ratification, not yet actioned as an actual `requirements.txt` addition
or a contract design). Check `proposals/to-orchestration/` first; if backend
hasn't ruled, that's the nudge to send, not new design work.

## BUILT (2026-07-25, later still) — Mission Engine wired into loop.py; autonomous missions are LIVE

The long-standing blocker at the top of this file ("Mission Engine built +
longevity-verified but not wired into loop.py") is closed. Ratified design:
`proposals/archive/to-backend/2026-07-25_mission-engine-loop-wiring-design.md`.
Built + proven, commit `01e0625`.

**Identity: `mission_id := session_id`** (one mission per session, v1) —
sidesteps a real blocker found by checking `core/memory/graph_schema.py`
directly: the graph's `Mission` node table has no session-correlation
column, and adding one would be a memory-specialist-tree schema change.
Reusing `session_id` makes "find the active mission for this session" a
targeted read, no scan, no schema change.

**`_sync_mission_state` (loop.py) runs every turn, before `run_turn`**:
re-reads the graph fresh (never trusts a carried-over `ctx`), sets/clears
`ctx.mission_id` — the exact line backend's budget-enforcement anchor now
reads fresh, per-LLM-call (their doc corrected from a ContextVar-mirror
approach after I flagged that pydantic-ai's concurrent tool execution can
make a set-once-in-a-tool-wrapper mirror invisible to the rest of a turn).
`_with_mission_context` folds active-mission state into the prompt.

**Three new native tools** (`start_mission`, `advance_mission`,
`end_mission`, `registry/capabilities/handler/support.py`) mirror
`spawn_batch`'s guarded shape — `mission_id` server-minted, never
model-supplied. `advance_mission` is a thin pass-through to the
already-tested `run_operate_step` (§4/§6/§7 gates).

**`Ports.budget: BudgetPort` — a real, load-bearing addition, not a detail:**
`run_operate_step`'s budget pre-check fails closed to EMPTY when Redis isn't
seeded (true in every environment today), which would `BUDGET_PAUSE` every
mission on step one. `core/orchestrator/utils/unlimited_budget.py`'s
`UnlimitedBudget` is the swap seam — `wiring.py` wires it in now; backend
swaps it for their real Redis-backed anchor later, one line, once seeded +
`enforcement_enabled` flips on.

**A real bug caught by a failing test:** `run_operate_step`'s completion
gate needs the mission's own status ALREADY `PROPOSED_COMPLETE` before it
will evaluate a judgment — `apply_turn` never sets that on its own.
`advance_mission` now writes that transition explicitly in the same step
`completion_verdicts` are submitted. Found by
`test_advance_mission_progresses_then_completes_and_clears_mission_id`
failing on first run.

10 new tests (`tests/orchestrator_mission_wiring.py`) — real registry + a
hermetic `_FakeGraphPort` + the real `UnlimitedBudget`; start/advance/
complete/end + both refusal paths + the recursion guard + loop.py's own
read-first/fold-into-prompt wiring (fake capability door, no model — see
report_v38.md for why: `run_loop`'s `on_event` drives a pydantic-ai
streaming path `FunctionModel` can't take without a `stream_function` no
test here provides yet). Full detail: `reports/orchestration/report_v38.md`.

**Resume: waiting on backend's real budget anchor** (Redis-seeded,
`enforcement_enabled`) before `Ports.budget` swaps from the stub — not
blocking anything else. Otherwise autonomous missions are live: a mission
can be started, advanced, completed, or ended through the central
orchestrator's own tool calls, end to end.

## BUILT (2026-07-25, later same day) — patch-apply (fs.patch + fs.read line ranges)

The nav/patch-tooling design (`proposals/archive/to-backend/2026-07-25_
nav-patch-tooling-design.md`, ratified) split into a hard prerequisite
(backend/security's parallel track: `security/sanitizers/uploads.py`
rejects any archive upload outright today — traced, not assumed, before
proposing) and a piece gated on nothing: patch-apply. Built + proven,
commit `24b5227`. `fs.read` gained optional `start_line`/`end_line`
(backward-compatible, `cat -n`-style numbered slice); new `fs.patch`
(`tools/file_patch.py`, `PermissionLevel.WRITE`) replaces/inserts/deletes a
precise line range via read-modify-write, no new `WorkspacePort` method.
Line-range over literal unified-diff, deliberately (no fuzzy
context-matching, more robust for an LLM caller citing line numbers it just
read). Reframed as a correctness FIX, not just a CB2 feature: `fs.read`'s
40k-char truncation + `fs.write`'s whole-file overwrite meant `code.engineer`
— already shipped in the engineering batch — could silently clobber
everything past the truncation point when editing a large file.

Wired through the three-places checklist (found while building the batch,
applied to myself this time): `tools/file_patch.py`, `code.engineer`'s
`tools` tuple, `batches.yaml`'s `engineering.tool_keys` — plus two
security-sensitive-permission pin lists (`tests/orchestrator_registry.py`,
`tests/expert_contract.py`) that would have regressed silently otherwise
(both caught by their own tests failing loudly).

Also closed two small interleaved items from security's review of the
shipped batch: `registry/config/batches.py`'s loader now rejects
NETWORK/ELEVATED grants fail-closed (`6d7ce9f`), and a stale `experts.py`
comment fixed (`7d7debd`). Full detail: `reports/orchestration/report_v37.md`.

**Resume: waiting on backend/security's archive-modality + cap work
(parallel track, not blocking anything of mine).** Once it lands: build the
extraction step into `_seed_inputs()` (§3 of the ratified design — reuses
`write_bytes`'s existing confinement, adds the entry-count/total-size/
per-member-size caps that don't exist yet), then AST-aware search
(`tree-sitter`, approved in principle, actual dependency addition deferred
to that build), then dependency-graph traversal (built on the AST tool's
output). Nothing else blocking in the meantime.

**§3 build-order coordination note, recorded now so it isn't lost (backend,
low-pri, 2026-07-25 — security's archive-acceptance design is ratified,
floors placed):** when §3 finally builds, (1) call `security.sanitizers.
pre_sanitization.run(member_bytes)` per extracted member BEFORE
`workspace.write_bytes`, reject the WHOLE archive on any block — no partial
extraction, a silently-dropped repo file is worse than a rejected upload;
(2) read the caps from `settings.SECURITY.archive_max_entries` (10000) /
`archive_max_uncompressed_ratio` (20, D8-ceilinged) / `INTAKE.
max_input_size_bytes` (per-member) — NOT local constants, same
single-sourced-floor pattern `tools.py` already uses for the text
sanitizer; (3) Layer-2 caps must be BYTE-VERIFIED during decompression
(bounded read as you go, never trust `ZipInfo.file_size`, which is
attacker-controlled metadata); (4) never recreate an OS symlink from a
member's `external_attr` — zip-slip stays closed only as long as every
member goes through `write_bytes` as plain bytes, never as a filesystem
symlink op.

## BUILT (2026-07-25) — the first concrete batch: engineering (CB2), proven end-to-end

Design ratified same-session (`proposals/archive/to-backend/2026-07-25_
engineering-batch-design.md`); built + proven, commit `dfaec88`. `backend/
batches.yaml` (one entry, `engineering`: `code.engineer`, tools `fs.read/
fs.write/code.run`, grants `READ/WRITE/EXECUTE`) + `registry/config/batches.py`
(fail-closed loader, mirrors `models.py`) + `wiring.py`'s one-line
`batch_registry=load_batches()` — `has_batches` is `True` in production now;
`spawn_batch` is live on the central orchestrator's tool list.

**Real, non-obvious trap found while building (not by a failing test):**
a batch's `tool_keys` must name every tool its member experts individually
need — `ExpertHandler._toolbox_for()` INTERSECTS the batch's tool scope
against each expert's own requested tools, so an omitted tool silently
strips it from the expert too, even though the batch's own top-level model
never sees workspace tools directly (`run_turn` filters `wants_workspace`
tools out at every tier). Full trace: `capability.py:130` (the filter) →
`experts.py:200` (`_toolbox_for`'s intersection) → `tools.py:60`
(`scoped()`'s compose-never-widen docstring).

**Proof:** `tests/orchestrator_engineering_batch.py`, 3 tests, real registry
+ real `batches.yaml` + real `code.engineer` (not fakes) — central → `spawn_
batch` → the batch's own scoped turn → the expert → a real `fs.write` against
a real workspace, plus a fault-path proving `FAILED` records without
crashing the central turn. `think()` has no `model=` override (unlike
`run_turn`), so `core.llm.framework.model_for_layer` is patched per-test to
reach that third tier — a test-infra gap worth a small deliberate follow-up
if a future expert-level test needs the same reach, not bundled in here.

**Explicit, not silent (ratified design §6):** this proves the batch
MECHANISM, not CB2's actual large-repo target — `code.engineer` still has
only whole-file tools (no AST search, dep-graph traversal, patch-apply).
Fast-follow, now unblocked to propose: those tools, each needing its own
decomposition-test pass, plus the prerequisite "how does a large repo enter
the ephemeral no-network `WorkspacePort` at all" design question underneath
them. Full detail: `reports/orchestration/report_v36.md`.

**Resume: security is reviewing the ratified design's grants/scoping in
parallel (backend's note) — fold in anything it flags before proposing a
second batch.** Otherwise nothing blocking; the natural next items are (a)
the nav/patch-apply tooling fast-follow, or (b) a second batch (e.g.
research) once backend/owner prioritize it.

## RESUMED (2026-07-25) — engineering-batch design filed, awaiting ratification

Pause lifted (`proposals/to-orchestration/2026-07-25_RESUME-concrete-batch-
UNPARKED.md`). Re-verified the PAUSED research below against current repo state
before acting on it — nothing drifted in `core/orchestrator/`, `registry/`,
`experts/`, `tools/` in the 2.5 weeks since (confirmed via `git log
1b30a1e..HEAD` scoped to those paths: only the pause-handoff commit itself and
one unrelated foundation-constant removal). Filed the design proposal:
`proposals/to-backend/2026-07-25_engineering-batch-design.md` — resolves the
open decision below (ship v1 on `code.engineer`'s current tools, fast-follow
the heavy nav/patch tools separately) and flags two corrections found while
re-tracing the actual code rather than trusting the wake messages' paraphrase:
(1) `config/` consolidated to a single `business.yaml` since this was last
discussed — a `batches.yaml`-equivalent belongs beside `models.yaml`
(`backend/batches.yaml` + `registry/config/batches.py`), not under
`config/backend/`; (2) `BatchDefinition` has no `model_role` field and
`Capabilities.run_turn` hardcodes the `"orchestrator"` role at every tier
today — proposed v1 ships without a per-batch override.

**Also traced one non-obvious correctness point the design proposal spells
out in full** (`Capabilities.scoped_to()` → `ExpertHandler._toolbox_for()`):
a batch's `tool_keys` must include every tool its member experts individually
need (not just what the batch's own top-level model calls directly), because
the expert's own toolbox is built by INTERSECTING the batch's tool scope
against the expert's requested tools — an engineering batch that omitted
`fs.read`/`fs.write`/`code.run` from `tool_keys` would silently hand
`code.engineer` an empty toolbox inside the batch.

**Resume: waiting on backend's ratification** (file location call + model_role
call) before building. Nothing else pending.

## PAUSED (backend-agent, weekly limits) — clean stop, 2026-07-06

**Tree state: clean.** `git status` empty, `HEAD` == `origin/main` (0 ahead,
0 behind) at commit `1b30a1e` (the CancelledError fix — see the update just
below). No uncommitted or half-finished code anywhere in
`core/orchestrator/`/`registry/`. Nothing was parked because nothing was
mid-write: backend asked me to start the concrete engineering-batch
proposal (see below), and I had only reached the research phase (no code,
no draft proposal file yet) when the pause landed.

**Exact next step, so this doesn't need re-deriving:** write the
propose-first design for the FIRST concrete batch — `engineering` (the CB2
Large Repo Understanding flagship, `docs/architecture/BATCH_ARCHITECTURE.md`
§7) — covering the decomposition-test pass, the `config/backend/batches.yaml`
content backend should place, and the end-to-end proof plan. Backend said
"Design → I ratify → build one + prove before a second"; nothing should be
built until that ratification lands.

**Research already done for that proposal (don't re-run it):**
- Expert domains (9, unchanged from the batch-orchestrator-design-v2 count):
  `code, web, summary, data, docs, verification, synthesis, delivery, media`.
  Tool domains are a SEPARATE namespace: `fs, code, text, http, memory,
  search, math, viz, web`.
- `code.engineer` (`experts/code/expert.py`) is the one existing
  engineering-judgment expert: tools `fs.read, fs.write, code.run`,
  `PermissionLevel.EXECUTE`, workspace-backed (Docker sandbox via
  `WorkspacePort`, ephemeral + network-less per run). Decomposition-test
  verdict: **one expert is the right shape** — write/run/read-failures/fix
  is one iterative judgment loop, not genuinely different expertise per
  phase. `verification.claims` (citation fact-checking against web sources)
  is a different judgment and should NOT be folded in.
- **The gap is tools, not experts** — CB2's three flagship capabilities
  (AST-aware search, dependency-graph traversal, precise patch-apply) do
  **not exist anywhere in `tools/`** today. Closest substitutes: `fs.read`
  (whole-file, 40k-char cap, no line ranges), `fs.write` (whole-file
  overwrite, no patch-apply), `text.diff` (computes a diff between two
  inline strings — cannot read/write a file or apply a diff to one).
  `WorkspacePort` itself is per-run/ephemeral/no-network — no mechanism to
  load or persist a large repo across runs. **This means the engineering
  batch proposal is NOT just a YAML entry wiring existing pieces — it needs
  new tool(s) proposed too** (at minimum: a patch-apply tool; AST search and
  dep-graph traversal are the harder open design questions — how a repo
  gets INTO the ephemeral workspace at all is the prerequisite question
  underneath those).
- `PermissionLevel` is a flat set (`READ, WRITE, EXECUTE, NETWORK,
  ELEVATED`), checked by membership not hierarchy
  (`ToolHandler.call_tool`, `tools.py:89`). An engineering `BatchDefinition
  .grants` would be `frozenset({READ, WRITE, EXECUTE})` — NETWORK
  deliberately excluded (sandbox has none anyway; matches the existing
  no-memory-write+no-egress-together posture).

**Open decision for whoever resumes, not yet answered:** does the
engineering batch ship v1 with `code.engineer`'s CURRENT tools (accepting
CB2's large-repo target is NOT met yet, just the batch MECHANISM proven
end-to-end on a small/medium repo), or does it block on the new
navigation/patch tooling landing first? Leaning toward the former (prove
the batch mechanism first per Prime Directive bottom-up order, propose the
heavy tools as a fast-follow) but this needs to be an explicit call in the
proposal, not defaulted silently.

## Update (2026-07-06 session, latest of all) — B1-item-3: spawn_batch consumes BatchAwarenessPort

`spawn_batch` (`registry/capabilities/handler/batches.py`) now calls
`cross_batch_awareness()` before a batch's scoped turn (folded into its own
task prompt) and `record_batch_status()` around it (ACTIVE → DONE/FAILED),
keyed on a per-invocation `batch_id` (uuid), with `BatchDefinition.domain`
carrying the stable batch_key. `Ports.awareness` + `Capabilities.open(...,
awareness=...)` thread the port from `wiring.py`; `scoped_to()` gets no
equivalent (unchanged recursion guard). Commit `9e0aa19`, 7 new tests, full
detail in `reports/orchestration/report_v34.md`. Design ratified:
`proposals/archive/to-backend/2026-07-06_b1-item3-batch-awareness-consumption-design.md`.

**Depends on backend's `mission_id`/`batch_id`-on-`VrakshaContext` placement**
(`478f34e`) — `ctx.batch_id` itself is reserved/unused by this build (a
concurrent-agent edit landed mid-session clarifying it must stay a LOCAL
var, never written onto the shared `ctx`, since `scoped_to()` reuses that
same object across concurrent batches — this build already matched that
shape, nothing to fix). Everything here fails closed to a no-op while
`ctx.mission_id == ""` (today's only real production value, since the
Mission Engine isn't wired into `loop.py` yet) — see the next paragraph.

**Resume: production end-to-end proof is still gated on wiring the Mission
Engine into `core/orchestrator/loop.py`** (unchanged blocker, tracked below) —
that's what would ever set `ctx.mission_id` to something real. The
awareness-consumption code itself is fully unit-tested today against a fake
port + a test `ctx` carrying a real `mission_id`. Next real item toward "one
batch end-to-end": a concrete first batch (`engineering`/CB2 flagship,
`config/backend/batches.yaml`) — a separate decomposition-test proposal, not
started.

## Update (2026-07-06 session, earlier) — §7 autonomy ceiling now config-driven (D7)

Minor but worth knowing if you're touching `mission_operate.py`'s autonomy
gate: `DEFAULT_AUTONOMOUS_SAFE` is gone. `needs_approval()`/
`run_operate_step()`'s `autonomous_safe` parameter now defaults from
`settings.SECURITY.autonomous_safe_permissions` (`config/backend/
security.yaml`, owner docket D7) — value unchanged (`frozenset({READ})`),
but the CEILING it can never exceed (`_AUTONOMOUS_SAFE_CEILING`, blocking
WRITE/EXECUTE/NETWORK/ELEVATED from ever being autonomous) now lives as a
non-YAML-overridable constant in `settings.py`, enforced fail-loud at
import. If a future mission ever needs broader autonomous action, that's a
deliberate ceiling-widening code change with owner sign-off, not a config
edit. Full detail: `reports/orchestration/report_v28.md`. This also closed
the whole config-depth track (reports v26-v28) — unrelated to Mission Engine
progress itself, just landed the same tree.

## Update (2026-07-06 session, earlier) — BatchHandler/spawn_batch built

Backend placed `ctx.batch_findings` on `VrakshaContext` (`57cde08`), clearing
the last named blocker. Built `BatchDefinition`/`BatchHandler`
(`registry/capabilities/handler/batches.py`, new) + `BatchFindings`/
`BatchSummary`/`SpawnBatchArgs` schemas — mirrors `ExpertHandler` one tier up,
wired as ONE new native tool (`spawn_batch`) on the central orchestrator via
`Capabilities.open()`/`OrchestratorDeps`/`build_orchestrator_tools`. Full
detail: `reports/orchestration/report_v25.md`.

**Two things resolved before writing code, both load-bearing:**
- Recursion guard: `Capabilities.scoped_to()` has NO `batch_registry`
  parameter — only `Capabilities.open()` does — so a batch's own scoped
  gateway can never spawn another batch. Structural, not a runtime check;
  proved with a real nested `run_turn`, not attribute inspection.
- Non-empty-registry gate: `spawn_batch` is offered to the model only when
  `BatchHandler.has_batches`. No `batches.yaml` exists yet, so today's real
  `Capabilities.open(ctx)` call site correctly never offers it — no dead
  surface, appears automatically the moment a real batch is configured.

9 tests (`tests/orchestrator_batch_handler.py`), including a discriminating
end-to-end test driving a REAL nested `run_turn` through one shared
`FunctionModel` spy. Suite green: 1134 passed, 13 env-skips. Committed.

**Resume: nothing is currently blocked.** `config/backend/batches.yaml` +
a first concrete batch proposal is the natural next step, but that's a
propose-first decomposition exercise (design's §H), not mine to start
unprompted. One low-priority gap flagged to backend, not fixed here:
`proposals/to-backend/2026-07-06_batch-call-audit-gap.md` (no
`ctx.batch_calls` equivalent to `ctx.expert_calls`) — currently unreachable,
revisit once a real batch lands. The unwired advisory batch-entropy scorer
still just needs a test (backlog, unchanged across several sessions now).

## Update (2026-07-06 session, earlier) — mission_compaction.py now consumes edges_of()

Self-selected cleanup, not owner-assigned: `edges_of()` landed on `GraphPort`
(`foundation/contracts/graph.py`, `45b6ab4`) explicitly to close the
restart-survival gap flagged below and in
`proposals/archive/to-backend/2026-07-06_task-edge-read-gap.md`. Consumed it:
`mission_compaction.py`'s in-session-only `MissionWorkingContext.dependents`
mirror is gone, replaced by `graph_compaction_eligible_tasks(graph, scope,
state)` reading BLOCKS/FEEDS straight from the graph (fails closed — `None`,
not an empty set, on a degraded read). `compact_working_context` now takes a
precomputed `eligible` set so the ACTION itself stays pure/graph-free.
Direction (`src=depended-on task, dst=dependent`) proven against the real
`GraphManager`, not a hand-rolled fake — a fake would have been a circular
oracle for exactly the thing that needed proving. Full detail:
`reports/orchestration/report_v24.md`. Suite green before commit.

**Resume: `BatchHandler`/`spawn_batch`/`ctx.batch_findings` are still the
next real frontier item, unchanged — still blocked on backend placing
`ctx.batch_findings` on `VrakshaContext`.** This update doesn't move that;
it was same-tree correctness cleanup on an already-shipped, not-yet-wired
component.

## Update (2026-07-06 session, earlier) — scoped-handler mechanism built

Design v2 ratified (all 5 points); built the scoped-handler mechanism
(`ExpertHandler.scoped()`, `Capabilities.scoped_to()`, `run_turn` filtering,
default-excludes-`remember`) — commit `5067bad`, full detail
`reports/orchestration/report_v23.md`. Found + fixed a real composability
bug along the way (`ToolHandler.scoped()` was replace-not-intersect;
proved it was load-bearing by reverting and re-confirming the new test
failed without the fix).

**Resume: `BatchHandler`/`spawn_batch`/`ctx.batch_findings` are next, but
blocked on backend placing `ctx.batch_findings` on `VrakshaContext`
(foundation, their seam) — no rush stated, check
`proposals/to-orchestration/` for that placement or a nudge-worthy gap
before building it.** Memory's cross-batch awareness slice landed in
parallel this session too (uncommitted at last check) — worth confirming
it's committed before consuming it.

## Update (2026-07-06 session, earlier) — batch-orchestrator design filed

§9 held (see the update just below) and backend cleared the gate + sent the
batch-layer split. Authored the propose-first sub-design:
`proposals/archive/to-backend/2026-07-06_batch-orchestrator-design-v2.md`
(full detail: `reports/orchestration/report_v22.md`). Nothing built — this is
design-only, awaiting ratification. **Resume: check
`proposals/to-orchestration/` for backend's ruling before writing any batch
code.** The Mission Engine itself needs nothing further right now; this file
stays the resume point for it, but the active frontier has moved to the
batch orchestrator (tracked in the report, not duplicated here).

## Update (2026-07-06 session, earlier) — §9 COMPLETE; §8 compaction built; waiting on batch split

§9's acceptance bar is now fully covered: restart survival + budget
pre-check + completion gate (`mission_operate.py`, prior update below) and
mid-run compaction (`mission_compaction.py`, new — 8 tests, commit
`a752e7a`). Full detail: `reports/orchestration/report_v21.md` (reports are
now one-file-per-feature, per `CLAUDE.md`'s updated Working Rules — don't
append further updates here to that old monolith pattern; this file
(HANDOFF) stays a running resume-point log, that's different from
reports/).

**Real limitation, load-bearing for whoever resumes next:** compaction's
frontier check (`MissionWorkingContext.dependents`) is IN-SESSION ONLY —
`GraphPort` has no way to read TASK dependency edges back after they're
written (`depends_on`/`dependents_of`/`breaks_if_removed` are hardcoded to
CodeFile/IMPORTS; `members()` returns nodes only). Flagged to backend,
non-blocking: `proposals/archive/to-backend/2026-07-06_task-edge-read-gap.md`.
If the batch orchestrator ever needs cross-restart dependency reasoning,
this is the seam that needs filling first — don't assume it already works.

**Told backend §9 is solid; waiting on the batch-layer work split**
(batch orchestrator ownership + cross-batch slice + context-discipline
bounds) — per the Prime Directive, backend is holding that split until §9
was green, which it now is. Nothing to build until it arrives; check
`proposals/to-orchestration/` on next resume.

**Still not built, unchanged from the prior update:** wiring
`run_operate_step`/`conclude_mission` into `core/orchestrator/loop.py`
(deliberately deferred — this IS the gate the batch orchestrator crosses,
not a shortcut), and the `awaiting_approval → active` resume path.

## Update (2026-07-06 session, earlier still) — §6 operate-step BUILT + committed

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
