"""
Memory hydration prefetch — a pipeline stage that starts hydration RIGHT AFTER
normalization so it overlaps the verifier's LLM call instead of being awaited serially
by the orchestrator. Net effect for ordinary turns: by the time the orchestrator runs,
memory is already hydrated, and the turn pays max(verify, hydrate) instead of verify +
hydrate. Explicitly hard continuity questions may then pay one bounded deep-reader call
after verification; blocked and simple turns never do.

It is NON-BLOCKING and INVISIBLE:
  * it kicks hydration off as a background future on the context and returns immediately,
    passing the payload through unchanged (so the verifier runs next, concurrently);
  * it emits NOTHING to the decision log — memory should feel like the assistant simply
    knowing things, never like it is "fetching memory".

Best-effort: a fast-path fault yields honest empty context; a deep-reader fault keeps
already-ready fast context. Neither fails the turn.
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
    """Resolve fast context, then deepen hard verified queries before orchestration."""
    started = time.monotonic()
    ctx = flow.ctx
    payload = await flow.load()
    hydration = HydrationPackage()
    try:
        request = None
        future = ctx.hydration_future
        if future is not None:
            hydration = await future
        elif ctx.normalized_input is not None and ctx.user_id:
            from . import manager

            request = HydrationRequest.for_turn(ctx, ctx.normalized_input)
            hydration = await manager.hydrate(request)
        verdict = ctx.verifier_result
        verified = bool(
            verdict is not None
            and getattr(verdict, "proceed", False)
            and not getattr(verdict, "dangerous", False)
            and not getattr(getattr(verdict, "threat_level", None), "should_block", False)
        )
        if verified and ctx.normalized_input is not None and ctx.user_id:
            from . import manager

            request = request or HydrationRequest.for_turn(ctx, ctx.normalized_input)
            # collect runs only after verifier passes. Keeping the generative reader
            # here prevents unsafe/blocked input from buying a model call during the
            # pre-verifier overlap while preserving fast deterministic prefetch.
            try:
                hydration = await manager.deepen(request, hydration)
            except Exception as exc:  # noqa: BLE001 — preserve already-ready fast context
                log.warning(
                    "deep memory retrieval degraded; using fast context: %s: %s",
                    type(exc).__name__,
                    exc,
                )
                hydration = HydrationPackage(
                    items=list(hydration.items),
                    token_budget=hydration.token_budget,
                    degraded=True,
                    notes="deep memory retrieval temporarily unavailable; using fast context",
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
