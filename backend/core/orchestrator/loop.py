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

import logging

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

log = logging.getLogger(__name__)


async def run_loop(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> OrchestratorResponse:
    """Run one orchestration turn and return a draft response."""
    hydration = await _hydrate(normalized, ports, ctx)

    async def on_event(event: dict) -> None:
        """Stream each capability call to the decision-log sink, live — EXCEPT internal
        plumbing. The orchestrator's memory tool is INVISIBLE (memory must feel like the
        assistant simply knowing things, never like it is 'running a memory tool'), and
        `search_tools` is the framework's own capability-discovery step for deferred
        loading (W2) — neither is a user-meaningful action, so both stay out of the stream."""
        tool = str(event.get("tool", "?"))
        if tool.startswith("memory.") or tool == "search_tools":
            return
        # Lift a string `query` arg (recall, web search, ...) to the top of detail so the UI
        # gets a clean `meta.query` to render — the wire mapper stringifies nested values, so
        # the query would otherwise survive only inside a stringified `meta.args` blob.
        detail = dict(event)
        args = event.get("args")
        if isinstance(args, dict) and isinstance(args.get("query"), str):
            detail["query"] = args["query"]
        await ports.log.emit(DecisionLogEntry(kind="tool_call", message=f"calling {tool}", detail=detail))

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


# With no `say()` note, a tool-free answer up to this length reads as a conversational CHAT reply
# (a greeting, a quick answer) → the chat bubble; longer than this it is a generated DELIVERABLE
# (a document/report) and goes to the deliverable channel, never the chat.
_CHAT_REPLY_MAX_CHARS = 600


def _split_message_and_deliverable(answer: OrchestratorAnswer, ctx: VrakshaContext) -> tuple[str, str]:
    """Split a turn into (conversational message, deliverable) — the two channels the UI renders
    separately (the chat bubble vs the deliverable card). They must NOT bleed into each other: a
    generated document never belongs in the chat, and chat commentary never belongs in the document.

    - `message` = what the orchestrator streamed via `say()`: short conversational notes only.
    - `deliverable` = the referenced expert artifact, or the model's own answer text.

    When the orchestrator said a note (`say()`), that note is the chat and the answer/artifact is the
    deliverable — a generated document never lands in the chat bubble. With NO `say()`, a SHORT
    tool-free answer is a plain conversational reply (greeting, quick answer) and IS the chat bubble;
    a LONGER one — or any answer backed by an artifact/findings — is a generated deliverable and is
    routed to the deliverable channel, never dumped into the chat.
    """
    deliverable = _resolve_deliverable(answer, ctx)
    message = ctx.assistant_message or ""
    if message:
        return message, deliverable          # said a note → chat; the answer/artifact is the deliverable
    if not answer.deliverable_ref and not ctx.expert_findings and len(deliverable) <= _CHAT_REPLY_MAX_CHARS:
        return deliverable, ""               # a short, direct conversational reply IS the chat
    return message, deliverable              # a document / artifact-backed answer → deliverable only


async def _hydrate(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> HydrationPackage:
    """Hydrate memory for the turn — SILENTLY.

    Memory must feel like the assistant simply KNOWING things, so NOTHING about
    hydration ever reaches the user's decision log: no "requesting memory" notice, no
    degradation warning. A fault is logged internally and the turn proceeds without
    memory (augmentation, never a gate).

    Prefers the hydration prefetched right after normalization (so it overlaps the
    verifier's LLM call instead of being awaited serially here); falls back to hydrating
    now when no prefetch ran (e.g. a caller that drives stages directly)."""
    future = getattr(ctx, "hydration_future", None)
    try:
        if future is not None:
            hydration = await future
        else:
            hydration = await ports.memory.hydrate(HydrationRequest.for_turn(ctx, normalized))
    except Exception as exc:  # noqa: BLE001 — memory degrades silently, never fails a turn
        log.warning("memory hydration degraded: %s", exc)
        hydration = HydrationPackage(degraded=True, notes="memory temporarily unavailable")
    ctx.hydration_items = list(hydration.items)
    if hydration.degraded and hydration.notes:
        log.info("memory hydration degraded this turn: %s", hydration.notes)  # internal log only
    return hydration
