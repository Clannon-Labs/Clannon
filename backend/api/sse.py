"""
Server-Sent Events streaming for a run.

`sse_stream` replays a run's buffered events, then live ones, as SSE frames — the
transport behind the frontend's RunEvent SSE contract. A terminal-and-already-streamed
run short-circuits after the replay so reconnections to a finished run don't hang.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from .run_state import RunState

_TERMINAL = {"delivered", "blocked", "failed"}


async def sse_stream(run: RunState) -> AsyncGenerator[str, None]:
    """Replay buffered events, then live ones, as SSE frames."""
    queue: asyncio.Queue = asyncio.Queue()
    run.subscribers.append(queue)
    try:
        for event in list(run.events):
            yield f"data: {json.dumps(event)}\n\n"
        if run.status in _TERMINAL and run.report is not None:
            return
        while True:
            event = await queue.get()
            if event is None:
                return
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        run.subscribers.remove(queue)
