"""
Memory hydration prefetch — a pipeline stage that starts hydration RIGHT AFTER
normalization so it overlaps the verifier's LLM call instead of being awaited serially
by the orchestrator. Net effect: by the time the orchestrator runs, memory is already
hydrated, and the turn pays max(verify, hydrate) instead of verify + hydrate.

It is NON-BLOCKING and INVISIBLE:
  * it kicks hydration off as a background future on the context and returns immediately,
    passing the payload through unchanged (so the verifier runs next, concurrently);
  * it emits NOTHING to the decision log — memory should feel like the assistant simply
    knowing things, never like it is "fetching memory".

Best-effort: a fault yields empty prepared context and never fails the turn.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from foundation import Flow, HydrationPackage, HydrationRequest, Origin

log = logging.getLogger(__name__)


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Start memory hydration in the background and pass the flow through unchanged."""
    started = time.monotonic()
    ctx = flow.ctx
    payload = await flow.load()
    try:
        from . import manager  # the MemoryPort singleton (lazy; avoids an import cycle)

        normalized = getattr(ctx, "normalized_input", None)
        if normalized is not None and getattr(ctx, "user_id", ""):
            request = HydrationRequest.for_turn(ctx, normalized)
            # fire-and-track: this module's collect stage awaits it after verification
            ctx.hydration_future = asyncio.ensure_future(manager.hydrate(request))
    except Exception as exc:  # noqa: BLE001 — prefetch is best-effort
        log.warning("memory hydration prefetch skipped: %s", exc)
    return flow.next(payload, Origin.MEMORY, started)


async def collect(flow: Flow[Any]) -> Flow[Any]:
    """Resolve prepared context before orchestration, behind the memory boundary."""
    started = time.monotonic()
    ctx = flow.ctx
    payload = await flow.load()
    hydration = HydrationPackage()
    try:
        future = ctx.hydration_future
        if future is not None:
            hydration = await future
        elif ctx.normalized_input is not None and ctx.user_id:
            from . import manager

            hydration = await manager.hydrate(
                HydrationRequest.for_turn(ctx, ctx.normalized_input)
            )
    except Exception as exc:  # noqa: BLE001 — augmentation never gates a turn
        log.warning("memory hydration degraded: %s", exc)
        hydration = HydrationPackage(
            degraded=True, notes="context preparation temporarily unavailable"
        )
    ctx.hydration_items = list(hydration.items)
    if hydration.degraded and hydration.notes:
        log.info("context preparation degraded this turn: %s", hydration.notes)
    return flow.next(payload, Origin.MEMORY, started)
