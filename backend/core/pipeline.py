"""
Core pipeline entry point — the single end-to-end runner.

The pipeline is the spine of Vraksha: it declares the order a request travels
through (`ACTIVE_STAGES`) and is the ONLY place that runs a turn end to end. Every
entry point (CLI, API, tooling) calls `run()`; nothing else re-walks the stages.

Each stage is a `Stage`: a Flow-in/Flow-out coroutine plus the presentation
metadata callers display (a CLI `label` and an API `status`). Keeping that metadata
ON the stage means there is ONE list to edit — no parallel arrays positionally
zipped against this one that silently drift when a stage is added, reordered, or
removed.

Removing a layer is a one-line edit here — comment out its `Stage` and the rest
still runs, because:
  * `Flow.then` skips a blocked/failed flow automatically (Railway short-circuit), and
  * the verifier and orchestrator `NormalizedInput.coerce()` whatever payload reaches
    them, so dropping the normalizer just means they see un-normalized input,
    dropping the sanitizer means they see un-sanitized input, and dropping the
    filter means delivery sends the orchestrator's draft unchanged.
No stage hard-depends on an earlier one being present (intake is the entry gate
that establishes identity, size limits, and modality detection).

    raw input
        -> intake        rate limit, size check, modality detection
        -> sanitizer     ClamAV/YARA pre-gate + modality sanitizer workers
        -> normalizer    code-only NormalizedInput construction
        -> verifier      structured safety/routing verification
        -> orchestrator  Vraksha-owned reasoning loop (experts + tools + memory)
        -> filter        structured safety/groundedness gate on the draft
        -> delivery      sets final_response and delivers

Observation is injected, never embedded: callers pass `on_stage`/`on_stage_end` to
watch progress and `decision_log` to capture the live decision stream, so the
server and the TUI share this one driver instead of copying the stage loop.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from foundation import Flow, constants
from core import intake, normalizer, verifier, orchestrator

log = logging.getLogger(__name__)
from core.memory import prefetch as hydration_prefetch
from security.sanitizers import runner as sanitizer
from security.filter import run as output_filter_run
from delivery import run as delivery_run


StageFn = Callable[[Flow], Awaitable[Flow]]


@dataclass(frozen=True)
class Stage:
    """One pipeline stage: its Flow-in/Flow-out coroutine plus the presentation
    metadata callers render. `name` is the canonical id; `label` is the CLI
    activity-feed text; `status` is the API run status for this phase."""

    run: StageFn
    name: str
    label: str
    status: str


# The canonical pipeline. Comment a line out to drop that layer — the driver and
# Flow handle the rest, and downstream stages coerce/skip gracefully. This list is
# the single source of stage order, labels, and statuses.
ACTIVE_STAGES: list[Stage] = [
    Stage(intake.process,    "intake",       "taking it in",        "sanitizing"),
    Stage(sanitizer.run,     "sanitizer",    "scanning input",      "sanitizing"),
    Stage(normalizer.run,    "normalizer",   "normalizing",         "verifying"),
    # start memory hydration in the background so it overlaps the verifier (same
    # user-visible status/label as the verifier — memory is invisible).
    Stage(hydration_prefetch.run, "hydration_prefetch", "verifying", "verifying"),
    Stage(verifier.run,      "verifier",     "verifying",           "verifying"),
    Stage(orchestrator.run,  "orchestrator", "working",             "orchestrating"),
    Stage(output_filter_run, "filter",       "checking the answer", "filtering"),
    Stage(delivery_run,      "delivery",     "delivering",          "filtering"),
]


# Observation hooks: pure observers invoked by the driver. They must not change the
# flow's outcome (their return value is ignored). `on_stage` fires before a stage
# runs (status/label); `on_stage_end` fires after (e.g. reconciling expert state).
StageObserver = Callable[["Stage"], None]
StageEndObserver = Callable[["Stage", Flow], None]


async def drive(
    flow: Flow,
    stages: list[Stage],
    *,
    on_stage: StageObserver | None = None,
    on_stage_end: StageEndObserver | None = None,
) -> Flow:
    """
    Run `flow` through `stages` in order, Railway-style: a stage that blocks or
    fails short-circuits the rest (`Flow.then` returns the flow unchanged once it
    `should_stop`). `on_stage` fires before each stage that actually runs;
    `on_stage_end` fires after it returns. Commenting a stage out of `stages`
    simply removes it — nothing here is positionally coupled to the list.
    """
    for stage in stages:
        if flow.should_stop:
            break
        if on_stage is not None:
            on_stage(stage)
        flow = await flow.then(stage.run)
        if on_stage_end is not None:
            on_stage_end(stage, flow)
    return flow


async def run(
    raw_input: Any,
    session_id: str,
    user_id: str = "local-user",
    *,
    trace_id: str | None = None,
    stages: list[Stage] | None = None,
    prepare: Callable[[Flow], None] | None = None,
    decision_log: list | None = None,
    on_stage: StageObserver | None = None,
    on_stage_end: StageEndObserver | None = None,
) -> Flow:
    """
    Run one user turn through the active pipeline end to end. THE single entry point.

    raw_input    raw input exactly as received; intake owns size/modality detection,
                 so callers must not normalize or sanitize before this.
    session_id   session identifier (Flow context + intake rate limiting).
    user_id      identity, set once here; the sole downstream scope.
    trace_id     pin the run's trace id (the API pins it to the run id so captured
                 artifacts, stored under ctx.trace_id, are addressable by run id).
    stages       override the stage list (defaults to ACTIVE_STAGES; used by tests
                 and by callers that want to run a subset).
    prepare      called with the fresh Flow before any stage runs — seed context
                 the caller owns (conversation history, wiki entries, uploaded
                 input files, ...).
    decision_log a list-like swapped onto ctx.decision_log to observe the live
                 decision stream (an observability.DecisionLogSink in practice).
    on_stage / on_stage_end  progress observers (see drive()).

    On an output-filter rejection the orchestrator gets a bounded, fail-closed chance
    to revise (the single shared `recover_from_filter_block`, narrated on the decision
    log) before the run is treated as blocked — same recovery for CLI and web.

    Returns the final Flow; a blocked or failed stage short-circuits the remainder.
    """
    flow = Flow.new(raw_input, session_id, user_id=user_id, trace_id=trace_id)
    if decision_log is not None:
        flow.ctx.decision_log = decision_log
    if prepare is not None:
        prepare(flow)
    return await _drive_with_revision(
        flow,
        stages if stages is not None else ACTIVE_STAGES,
        on_stage=on_stage,
        on_stage_end=on_stage_end,
    )


def _split_at_filter(stages: list[Stage]):
    """Locate the orchestrator→filter segment for the bounded revision loop.

    Returns (pre, segment, post) when BOTH an `orchestrator` and a later `filter`
    stage are present; otherwise None, so a custom or subset stage list (tests,
    partial pipelines) runs as a plain linear drive with unchanged behaviour.
    """
    names = [s.name for s in stages]
    if "orchestrator" not in names or "filter" not in names:
        return None
    o, f = names.index("orchestrator"), names.index("filter")
    if f < o:
        return None
    return stages[:o], stages[o:f + 1], stages[f + 1:]


async def recover_from_filter_block(flow: Flow) -> Flow:
    """The single, shared, fail-closed output-filter recovery — used by BOTH the CLI
    pipeline and the web run driver, so the revision logic lives in exactly one place.

    The output filter rejected the orchestrator's DRAFT. Hand the rejection reason
    back (`ctx.filter_feedback`) and let the orchestrator RE-REASON — re-running only
    `run_loop`, NOT the whole orchestrator stage, so a rejected draft is never written
    to memory — then let the filter adjudicate the new draft. Bounded by
    `FILTER_MAX_REVISIONS`; after that the run stays blocked (fail closed — the filter
    is always the final authority). Each attempt is narrated on the shared decision
    log, so every surface (CLI feed, web SSE) sees the revision live.
    """
    from core.orchestrator.loop import run_loop
    from core.orchestrator.schemas import DecisionLogEntry
    from core.orchestrator.utils.wiring import build_default_ports

    ctx = flow.ctx
    while (
        ctx.filter_blocked
        and ctx.normalized_input is not None
        and ctx.filter_retry_count < constants.FILTER_MAX_REVISIONS
    ):
        ctx.filter_retry_count += 1
        ctx.decision_log.append(DecisionLogEntry(
            kind="warning",
            message=(
                f"output filter rejected the draft — revising "
                f"(attempt {ctx.filter_retry_count}/{constants.FILTER_MAX_REVISIONS})"
            ),
        ))
        # hand the reason back and clear the block so the re-reasoned draft is judged fresh
        ctx.filter_feedback = ctx.filter_block_reason
        ctx.blocked = False
        ctx.filter_blocked = False
        ctx.filter_block_reason = None
        try:
            ports = build_default_ports(ctx)
            revised = await asyncio.wait_for(
                run_loop(ctx.normalized_input, ports, ctx),
                timeout=constants.ORCHESTRATOR_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 — surface as a run failure, never crash
            ctx.failed = True
            ctx.failure_error = exc
            return flow
        ctx.orchestrator_response = revised
        flow = await output_filter_run(flow)
        ctx = flow.ctx
    ctx.filter_feedback = None
    return flow


async def _persist_turn_memory_if_delivered(flow: Flow) -> None:
    """Persist this turn's memory ONLY when the output filter ACCEPTED the draft and it
    was delivered.

    This is the post-filter write site: a blocked or failed draft never seeds memory, so
    the "rejected drafts never touch memory" invariant now holds on the INITIAL pass, not
    only inside the bounded revision loop. The actual write policy lives in the
    orchestrator (`persist_turn_memory`) — the pipeline owns only the TIMING. Best-effort:
    the answer is already delivered, so a memory fault must never fail the turn.
    """
    ctx = flow.ctx
    if ctx.blocked or ctx.failed or ctx.filter_blocked:
        return  # not delivered — never write
    try:
        await orchestrator.persist_turn_memory(ctx)
    except Exception as exc:  # noqa: BLE001 — answer already delivered; memory is best-effort
        log.warning("post-delivery memory persist dropped: %s", exc)


async def _drive_with_revision(
    flow: Flow,
    stages: list[Stage],
    *,
    on_stage: StageObserver | None = None,
    on_stage_end: StageEndObserver | None = None,
) -> Flow:
    """Drive the pipeline, then give the orchestrator a BOUNDED chance to revise when
    the output filter rejects its draft — via the shared `recover_from_filter_block`.

    The filter remains the sole content gate and adjudicates every attempt; recovery
    only turns a rejection from a silent dead-end into a feedback-driven retry, and
    NEVER delivers content the filter hasn't accepted. A stage list without an
    orchestrator+filter pair (tests/subsets) falls back to a plain linear drive.

    Memory for the turn is persisted ONCE, AFTER the filter accepts and the answer is
    delivered (`_persist_turn_memory_if_delivered`), so a blocked draft never seeds it.
    """
    split = _split_at_filter(stages)
    if split is None or constants.FILTER_MAX_REVISIONS <= 0:
        flow = await drive(flow, stages, on_stage=on_stage, on_stage_end=on_stage_end)
        await _persist_turn_memory_if_delivered(flow)
        return flow

    pre, segment, post = split
    # input gates + the first orchestrator→filter pass
    flow = await drive(flow, pre + segment, on_stage=on_stage, on_stage_end=on_stage_end)
    if flow.ctx.filter_blocked:
        flow = await recover_from_filter_block(flow)
    if flow.should_stop:
        return flow  # input-blocked, failed, or still filter-blocked after recovery — NO memory write
    flow = await drive(flow, post, on_stage=on_stage, on_stage_end=on_stage_end)  # delivery
    await _persist_turn_memory_if_delivered(flow)  # only now, on the delivered draft
    return flow
