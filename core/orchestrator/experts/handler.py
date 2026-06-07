"""
Expert handler — the orchestrator's door to experts.

Phase 1 is a stub, but it already enforces the two real contracts:
- the two-output split: a brief ExpertSummary goes back to the orchestrator while
  the full ExpertFindings is buffered in ctx.expert_findings for the output filter
  (the orchestrator never sees raw findings),
- bounded concurrency via EXPERT_MAX_CONCURRENT.

Each invocation is also recorded on ctx.expert_calls for audit.

TODO: real experts (research, code, media, citation, ...), each its own module
under experts/, selected by the router and run under least-privilege with their
own scoped tools.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from foundation import ExpertCallRecord, VrakshaContext, constants

from ..schemas import ExpertFindings, ExpertRequest, ExpertSummary


class StubExpertHandler:
    """Phase-1 ExpertHandlerPort implementation."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(constants.EXPERT_MAX_CONCURRENT)

    async def run_experts(
        self, requests: list[ExpertRequest], ctx: VrakshaContext
    ) -> list[ExpertSummary]:
        if not requests:
            return []
        return await asyncio.gather(*[self._run_one(req, ctx) for req in requests])

    async def _run_one(self, request: ExpertRequest, ctx: VrakshaContext) -> ExpertSummary:
        async with self._semaphore:
            started = time.monotonic()
            ref = uuid4().hex[:8]

            # Full findings -> ctx (for the output filter); orchestrator never reads these.
            ctx.expert_findings.append(
                ExpertFindings(
                    expert=request.name,
                    ref=ref,
                    full_content=(
                        f"[stub] expert '{request.name}' is not implemented yet; "
                        f"task was: {request.task}"
                    ),
                    metadata={"stub": True},
                )
            )

            ctx.expert_calls.append(
                ExpertCallRecord(
                    expert_name=request.name,
                    arguments={"task": request.task},
                    result={"finding_ref": ref},
                    success=True,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                )
            )

            # Brief summary -> orchestrator.
            return ExpertSummary(
                expert=request.name,
                summary=f"[stub] {request.name} produced no real findings yet",
                confidence=0.0,
                finding_ref=ref,
            )
