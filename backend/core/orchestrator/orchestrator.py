"""
Orchestrator stage — the layer's entry point.

A Flow stage like the others (`async def run(flow) -> Flow`). It builds the
default ports, runs the bounded reasoning loop under the orchestrator timeout,
stores the draft response on the context, and hands off. The orchestrator never
content-blocks (the verifier and the output filter
own that); a timeout, provider rate-limit storm, or loop fault degrades
gracefully (utils/recovery) to an honest, grounded answer rather than a blank
failure — the user never gets nothing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import settings
from foundation import (
    Flow,
    NormalizedInput,
    Origin,
    PipelineStage,
)

from .loop import run_loop
from .schemas import DecisionLogEntry
from .utils.recovery import build_degraded_response, classify_failure, degraded_reason
from .utils.wiring import build_default_ports

log = logging.getLogger(__name__)


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Pipeline entry point for orchestration."""
    started = time.monotonic()
    try:
        # coerce so the normalizer (and the whole input gate) is optional: a raw
        # payload becomes a valid NormalizedInput here. No-op when an upstream
        # stage already produced one.
        normalized = NormalizedInput.coerce(await flow.load())
        flow.ctx.advance(PipelineStage.ORCHESTRATING)
        ports = build_default_ports(flow.ctx)

        # Whole-turn wall clock: set ONE deadline at turn start. The initial pass (here)
        # and every filter-revision (pipeline.recover_from_filter_block) budget their
        # wait_for against the time remaining, so the turn can never exceed
        # TURN_WALL_CLOCK_S even across revisions. Fresh-turn deadline is well above
        # ORCHESTRATOR_TIMEOUT_S, so this first pass keeps its full budget.
        flow.ctx.turn_deadline = time.monotonic() + settings.ORCHESTRATOR.turn_wall_clock_s
        response = await asyncio.wait_for(
            run_loop(normalized, ports, flow.ctx),
            timeout=min(settings.ORCHESTRATOR.timeout_s,
                        max(0.0, flow.ctx.turn_deadline - time.monotonic())),
        )

        flow.ctx.orchestrator_response = response

        return flow.next(response, Origin.ORCHESTRATOR, started)

    except Exception as exc:
        # Graceful degradation: a timeout, a provider rate-limit storm, or an
        # unexpected fault must never hand the user a blank failure. Salvage an
        # honest, grounded answer from whatever the run already gathered (LLM-free
        # — another model call would only fail again under rate limits) and let it
        # flow on through the filter → delivery like any answer.
        kind = classify_failure(exc)
        log.warning("orchestrator degraded (%s): %s", kind, exc)
        flow.ctx.decision_log.append(
            DecisionLogEntry(kind="warning", message=f"answering in degraded mode: {degraded_reason(kind)}")
        )
        degraded = build_degraded_response(flow.ctx, kind)
        flow.ctx.orchestrator_response = degraded
        return flow.next(degraded, Origin.ORCHESTRATOR, started)
