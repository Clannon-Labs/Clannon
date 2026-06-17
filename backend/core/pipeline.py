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

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from foundation import Flow
from core import intake, normalizer, verifier, orchestrator
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

    Returns the final Flow; a blocked or failed stage short-circuits the remainder.
    """
    flow = Flow.new(raw_input, session_id, user_id=user_id, trace_id=trace_id)
    if decision_log is not None:
        flow.ctx.decision_log = decision_log
    if prepare is not None:
        prepare(flow)
    return await drive(
        flow,
        stages if stages is not None else ACTIVE_STAGES,
        on_stage=on_stage,
        on_stage_end=on_stage_end,
    )
