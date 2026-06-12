"""
Delivery stage — the final hand-off to the user's platform.

UI-agnostic: it sets ctx.final_response and delivers via the active adapter. The
checkpoint adapter is the CLI, which prints the streamed decision log followed by
the filtered answer. A frontend later connects the same way (drain the decision-log
queue, render the final response) with no change to this core.
"""

from __future__ import annotations

import os
import time
from typing import Any

from foundation import Flow, Origin, PipelineStage, VrakshaError


def _deliver_cli(flow: Flow[Any]) -> None:
    print("\n--- decision log ---")
    for entry in flow.ctx.decision_log:
        print(f"[{entry.kind}] {entry.message}")
    print("\n--- answer ---")
    print(flow.ctx.final_response or "(no answer produced)")


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Pipeline entry point for delivery."""
    started = time.monotonic()
    try:
        flow.ctx.advance(PipelineStage.OUTPUT)
        response = flow.ctx.orchestrator_response
        flow.ctx.final_response = response.text if response is not None else ""
        # interactive CLI renders the answer itself; quiet mode skips the raw dump
        if os.getenv("VRAKSHA_CLI_QUIET") != "1":
            _deliver_cli(flow)
        return flow.next(flow.ctx.final_response, Origin.OUTPUT, started)
    except Exception as exc:
        return flow.fail(VrakshaError(f"delivery failed: {exc}", cause=exc), Origin.OUTPUT, started)
