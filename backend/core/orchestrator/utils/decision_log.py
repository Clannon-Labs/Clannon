"""
Decision-log sink — the loop streams structured entries here as it works.

Minimal at the checkpoint: emit() appends to ctx.decision_log, which the delivery
layer reads to show the user what the orchestrator did and why. The
DecisionLogSink Protocol (ports.py) is the seam — a queue/SSE-backed sink for
live concurrent streaming drops in here later with no change to the loop.
"""

from __future__ import annotations

from foundation import VrakshaContext

from ..schemas import DecisionLogEntry


class CtxDecisionLog:
    """Appends decision-log entries to the request context."""

    def __init__(self, ctx: VrakshaContext) -> None:
        self._ctx = ctx

    async def emit(self, entry: DecisionLogEntry) -> None:
        self._ctx.decision_log.append(entry)
