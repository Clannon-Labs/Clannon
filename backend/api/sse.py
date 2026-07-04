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
        # Since the terminal-order fix (report_done strictly BEFORE status:delivered —
        # run_driver.py, pinned by tests/sse_terminal_order.py) a delivered run always
        # has its report by the time status flips, so a live delivered-but-report-None
        # window can't occur; the guard stays as defense for legacy/partial state.
        # Every no-report terminal (blocked / failed / cancelled) closes cleanly here
        # instead of hanging on the queue forever.
        if run.status in TERMINAL_STATUSES and not (run.status == "delivered" and run.report is None):
            return
        while True:
            event = await queue.get()
            if event is None:
                return
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        run.subscribers.remove(queue)
