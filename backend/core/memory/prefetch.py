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

Best-effort: a fault here just skips the prefetch and the orchestrator hydrates itself.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from foundation import Flow, HydrationRequest, Origin

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
            request = HydrationRequest(
                session_id=getattr(ctx, "session_id", "") or "",
                user_id=ctx.user_id,
                normalized=normalized,
                wiki=tuple(
                    (e.get("title", ""), e.get("content", ""))
                    for e in (getattr(ctx, "wiki_entries", None) or [])
                    if isinstance(e, dict)
                ),
            )
            # fire-and-track: the orchestrator awaits ctx.hydration_future
            ctx.hydration_future = asyncio.ensure_future(manager.hydrate(request))
    except Exception as exc:  # noqa: BLE001 — prefetch is best-effort; orchestrator falls back
        log.warning("memory hydration prefetch skipped: %s", exc)
    return flow.next(payload, Origin.MEMORY, started)
