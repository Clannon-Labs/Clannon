"""Post-delivery Memory Manager lifecycle stage.

Pipeline supplies neutral evidence from one accepted turn. Manager alone decides
whether to retain anything, which tier fits, and what provenance to persist.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from foundation import Flow, MemoryTurn, Origin

from . import manager

log = logging.getLogger(__name__)

# Strong references keep post-delivery curator tasks alive on server event loops.
_BACKGROUND: set[asyncio.Task] = set()


def _participants(ctx) -> tuple[str, ...]:
    names = [
        *(getattr(call, "expert_name", "") for call in ctx.expert_calls),
        *(getattr(call, "tool_name", "") for call in ctx.tool_calls),
    ]
    return tuple(dict.fromkeys(name for name in names if name))


def _turn(ctx) -> MemoryTurn | None:
    normalized = ctx.normalized_input
    response = ctx.final_response
    if normalized is None or response is None:
        return None
    decisions = tuple(
        getattr(entry, "message", "")
        for entry in ctx.decision_log
        if getattr(entry, "kind", "") in {"answer", "decision", "warning"}
        and getattr(entry, "message", "")
    )
    return MemoryTurn(
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        request=getattr(normalized, "content", "") or "",
        response=str(response),
        findings=tuple(
            getattr(finding, "full_content", "")
            for finding in ctx.expert_findings
            if getattr(finding, "full_content", "")
        ),
        decisions=decisions,
        participants=_participants(ctx),
    )


async def _process(turn: MemoryTurn) -> None:
    try:
        await manager.process_turn(turn)
    except Exception as exc:  # noqa: BLE001 — answer is already delivered
        log.warning("memory curator dropped completed turn: %s", exc)


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Hand accepted delivered evidence to Manager without delaying delivery."""
    started = time.monotonic()
    payload = await flow.load()
    turn = _turn(flow.ctx)
    if turn is not None and turn.user_id:
        task = asyncio.ensure_future(_process(turn))
        _BACKGROUND.add(task)
        task.add_done_callback(_BACKGROUND.discard)
    return flow.next(payload, Origin.MEMORY, started)
