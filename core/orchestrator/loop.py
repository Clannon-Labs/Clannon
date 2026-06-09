"""
The orchestrator reasoning core — UI-agnostic.

The orchestrator is a native tool-driving agent: its available tools and experts
are real tool schemas, and the model runs its own bounded tool loop. This module
hydrates memory, hands the turn to the capability gateway (`ports.caps.run_turn`),
streams a live decision log through the sink, and maps the agent's answer to an
OrchestratorResponse. The whole-turn timeout is applied by the stage
(orchestrator.py); turn/usage bounds + the graceful cap fallback live in the
gateway.
"""

from __future__ import annotations

from foundation import (
    HydrationPackage,
    HydrationRequest,
    NormalizedInput,
    OrchestratorResponse,
    VrakshaContext,
)
from registry.config import get_prompt

from .ports import Ports
from .schemas import DecisionLogEntry, OrchestratorAnswer
from .utils.prompt import build_user_prompt


async def run_loop(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> OrchestratorResponse:
    """Run one orchestration turn and return a draft response."""
    hydration = await _hydrate(normalized, ports, ctx)

    async def on_event(event: dict) -> None:
        """Stream each capability call to the decision-log sink, live."""
        await ports.log.emit(DecisionLogEntry(
            kind="tool_call",
            message=f"calling {event.get('tool', '?')}",
            detail=event,
        ))

    answer: OrchestratorAnswer = await ports.caps.run_turn(
        system_prompt=get_prompt("orchestrator").text,
        user_prompt=build_user_prompt(normalized, hydration),
        output_type=OrchestratorAnswer,
        on_event=on_event,
    )

    await ports.log.emit(DecisionLogEntry(kind="answer", message=answer.answer_text))
    return OrchestratorResponse(
        text=answer.answer_text,
        confidence=answer.confidence,
        finding_refs=[f.ref for f in ctx.expert_findings],
    )


async def _hydrate(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> HydrationPackage:
    """Ask the memory manager (via the port) for context before the turn."""
    await ports.log.emit(DecisionLogEntry(kind="hydration", message="requesting memory hydration"))
    hydration = await ports.memory.hydrate(
        HydrationRequest(session_id=ctx.session_id, normalized=normalized)
    )
    if hydration.notes:
        await ports.log.emit(DecisionLogEntry(kind="hydration", message=hydration.notes))
    return hydration
