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

    async def on_message(text: str) -> None:
        """The orchestrator's conversational voice (`say`): accumulate it for the turn
        AND stream it live as a `message` decision-log entry, so the user sees the agent
        talking WHILE experts work. Free-form commentary — never the filtered deliverable."""
        if not text:
            return
        ctx.assistant_message = (ctx.assistant_message or "") + text
        await ports.log.emit(DecisionLogEntry(kind="message", message=text))

    answer: OrchestratorAnswer = await ports.caps.run_turn(
        system_prompt=get_prompt("orchestrator").text,
        # revision_feedback is set only on a bounded retry after the output filter
        # rejected the previous draft — it tells the orchestrator what to fix
        user_prompt=build_user_prompt(normalized, hydration, ctx.filter_feedback, ctx.input_files),
        output_type=OrchestratorAnswer,
        on_event=on_event,
        on_message=on_message,
        # prior turns of this session, fed as real chat history so a follow-up
        # continues the conversation instead of re-reading a summary blob
        conversation=ctx.conversation,
    )

    await ports.log.emit(DecisionLogEntry(kind="answer", message=answer.answer_text))
    message, deliverable = _split_message_and_deliverable(answer, ctx)
    return OrchestratorResponse(
        text=deliverable,
        message=message,
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


def _split_message_and_deliverable(answer: OrchestratorAnswer, ctx: VrakshaContext) -> tuple[str, str]:
    """Split a turn into (conversational message, deliverable).

    The message is whatever the orchestrator streamed via `say()` this turn. The
    deliverable is the referenced expert artifact, or the model's own answer text.

    Robustness fallback: a turn that produced NO artifact and ran NO research is the
    orchestrator simply TALKING (a greeting, a clarifying question, a direct reply) —
    treat its answer text as the chat message, not a deliverable card, even if it did
    not explicitly call `say()`. A turn that DID research keeps its synthesized text as
    the deliverable; the message is just the (optional) framing it streamed.
    """
    deliverable = _resolve_deliverable(answer, ctx)
    message = ctx.assistant_message or ""
    if not message and not answer.deliverable_ref and not ctx.expert_findings:
        return deliverable, ""   # direct conversational turn: the answer IS the chat, no deliverable
    return message, deliverable


async def _hydrate(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> HydrationPackage:
    """Ask the memory manager (via the port) for context before the turn.

    Memory is augmentation, never a gate: any fault here degrades to an empty
    package and the turn continues — with an honest warning in the decision
    log, not a silent pretence that the user has no memory.
    """
    await ports.log.emit(DecisionLogEntry(kind="hydration", message="requesting memory hydration"))
    try:
        hydration = await ports.memory.hydrate(
            HydrationRequest(
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                normalized=normalized,
                # the user's wiki (set by the delivery layer) — loaded as the
                # highest-trust text tier, selected by relevance at hydration
                wiki=tuple(
                    (e.get("title", ""), e.get("content", ""))
                    for e in ctx.wiki_entries
                    if isinstance(e, dict)
                ),
            )
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
