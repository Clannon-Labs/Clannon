"""
Queue-backed decision-log sink.

The loop emits structured entries here as it works; a consumer (the TUI today, an
SSE/WebSocket transport in the frontend later) drains them via `stream()`. The
sink is UI-agnostic: the consumer holds no orchestration logic, it only reads.
Entries are also mirrored to ctx.decision_log for after-the-fact audit.

This makes a long-running loop with periodic user output possible without
changing the loop — a consumer can drain `stream()` concurrently while the loop
keeps running. Wiring that concurrent drain is the delivery layer's job (deferred).
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from foundation import VrakshaContext

from ..schemas import DecisionLogEntry


class QueueDecisionLogSink:
    """An asyncio.Queue sink that also mirrors entries onto the context."""

    _SENTINEL = object()

    def __init__(self, ctx: VrakshaContext, maxsize: int = 0) -> None:
        self._ctx = ctx
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._seq = 0

    async def emit(self, entry: DecisionLogEntry) -> None:
        """Stamp ordering, mirror to ctx, and enqueue for streaming consumers."""
        entry.seq = self._seq
        self._seq += 1
        self._ctx.decision_log.append(entry)
        await self._queue.put(entry)

    async def close(self) -> None:
        """Signal end-of-stream so a draining consumer can stop cleanly."""
        await self._queue.put(self._SENTINEL)

    async def stream(self) -> AsyncIterator[DecisionLogEntry]:
        """Yield entries as they arrive until close() is called."""
        while True:
            item = await self._queue.get()
            if item is self._SENTINEL:
                return
            yield item
