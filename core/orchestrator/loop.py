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
        text=_resolve_deliverable(answer, ctx),
        confidence=answer.confidence,
        finding_refs=[f.ref for f in ctx.expert_findings],
    )


def _resolve_deliverable(answer: OrchestratorAnswer, ctx: VrakshaContext) -> str:
    """The response text: a referenced expert artifact (full report, never seen by
    the orchestrator's model) when one is named, else the model's own answer."""
    if answer.deliverable_ref:
        for finding in ctx.expert_findings:
            if finding.ref == answer.deliverable_ref and finding.full_content:
                return finding.full_content
    return answer.answer_text


async def _hydrate(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> HydrationPackage:
    """Ask the memory manager (via the port) for context before the turn.

    Memory is augmentation, never a gate: any fault here degrades to an empty
    package and the turn continues — with an honest warning in the decision
    log, not a silent pretence that the user has no memory.
    """
    await ports.log.emit(DecisionLogEntry(kind="hydration", message="requesting memory hydration"))
    try:
        hydration = await ports.memory.hydrate(
            HydrationRequest(session_id=ctx.session_id, user_id=ctx.user_id, normalized=normalized)
        )
    except Exception:
        hydration = HydrationPackage(
            degraded=True, notes="memory temporarily unavailable; answering without it"
        )
    ctx.hydration_items = list(hydration.items)
    if hydration.notes:
        kind = "warning" if hydration.degraded else "hydration"
        await ports.log.emit(DecisionLogEntry(kind=kind, message=hydration.notes))
    return hydration
