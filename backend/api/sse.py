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

from .run_state import RunState, TERMINAL_STATUSES


async def sse_stream(run: RunState) -> AsyncGenerator[str, None]:
    """Replay buffered events, then live ones, as SSE frames."""
    queue: asyncio.Queue = asyncio.Queue()
    run.subscribers.append(queue)
    try:
        for event in list(run.events):
            yield f"data: {json.dumps(event)}\n\n"
        # A reconnect to a finished run has nothing more coming — replay, then close.
        # The one exception is a `delivered` run still streaming its report (status
        # flips to delivered while report stays None until the final delta): keep that
        # stream open so a mid-report reconnect gets the rest. Every no-report terminal
        # (blocked / failed / cancelled) closes cleanly here instead of hanging on the
        # queue forever (the old `report is not None` guard never closed them).
        if run.status in TERMINAL_STATUSES and not (run.status == "delivered" and run.report is None):
            return
        while True:
            event = await queue.get()
            if event is None:
                return
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        run.subscribers.remove(queue)
