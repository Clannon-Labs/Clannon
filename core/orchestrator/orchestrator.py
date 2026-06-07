"""
Orchestrator stage — the layer's entry point.

A Flow stage like the others (`async def run(flow) -> Flow`). It builds the
default ports, runs the bounded reasoning loop under the orchestrator timeout,
stores the draft response and proposed memory writes on the context, and hands
off. The orchestrator never content-blocks (the verifier and the future output
filter own that); infrastructure/loop faults fail the stage.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from foundation import Flow, OrchestratorError, Origin, PipelineStage, constants

from .loop import run_loop
from .utils.wiring import build_default_ports


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Pipeline entry point for orchestration."""
    started = time.monotonic()
    try:
        normalized = await flow.load()
        flow.ctx.advance(PipelineStage.ORCHESTRATING)
        ports = build_default_ports(flow.ctx)

        try:
            response = await asyncio.wait_for(
                run_loop(normalized, ports, flow.ctx),
                timeout=constants.ORCHESTRATOR_TIMEOUT_S,
            )
        finally:
            await ports.log.close()

        flow.ctx.orchestrator_response = response
        # Experts/orchestrator only PROPOSE memory writes; the manager owns persistence.
        await ports.memory.record_write_proposals(flow.ctx.memory_writes_requested)

        return flow.next(response, Origin.ORCHESTRATOR, started)

    except asyncio.TimeoutError as exc:
        return flow.fail(OrchestratorError("orchestrator timed out", cause=exc), Origin.ORCHESTRATOR, started)
    except OrchestratorError as exc:
        return flow.fail(exc, Origin.ORCHESTRATOR, started)
    except Exception as exc:
        return flow.fail(OrchestratorError(f"orchestrator failed: {exc}"), Origin.ORCHESTRATOR, started)
