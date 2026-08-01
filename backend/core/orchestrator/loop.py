"""
The orchestrator reasoning core — UI-agnostic.

The orchestrator is a native tool-driving agent: its available tools and experts
are real tool schemas, and the model runs its own bounded tool loop. This module
hydrates memory, hands the turn to the capability gateway (`ports.caps.run_turn`),
receives pipeline-prepared context, streams a live decision log through the sink, and maps the agent's answer to an
OrchestratorResponse. The whole-turn timeout is applied by the stage
(orchestrator.py); turn/usage bounds + the graceful cap fallback live in the
gateway.
"""

from __future__ import annotations

import logging

from foundation import (
    HydrationPackage,
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
    # Each run_loop call is a FRESH draft. On a filter-rejected → revised turn the same
    # ctx is reused, so clear the prior attempt's `say()` voice up front — otherwise the
    # rejected draft's conversational commentary concatenates (via on_message below) into
    # the delivered chat bubble. The live stream already emitted per attempt; this only
    # governs what the FINAL message carries.
    ctx.assistant_message = ""
    hydration = HydrationPackage(items=list(ctx.hydration_items))
    mission = await _sync_mission_state(ports, ctx)

    async def on_event(event: dict) -> None:
        """Stream each capability call to the decision-log sink, live — EXCEPT internal
        plumbing. `search_tools` is the framework's own capability-discovery step
        for deferred loading (W2), so it stays out of the stream."""
        tool = str(event.get("tool", "?"))
        if tool == "search_tools":
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

    user_prompt = build_user_prompt(normalized, hydration, ctx.filter_feedback, ctx.input_files)
    user_prompt = _with_mission_context(user_prompt, mission)
    answer: OrchestratorAnswer = await ports.caps.run_turn(
        system_prompt=get_prompt("orchestrator").text,
        # revision_feedback is set only on a bounded retry after the output filter
        # rejected the previous draft — it tells the orchestrator what to fix
        user_prompt=user_prompt,
        output_type=OrchestratorAnswer,
        on_event=on_event,
        on_message=on_message,
        # prior turns of this session, fed as real chat history so a follow-up
        # continues the conversation instead of re-reading a summary blob
        conversation=ctx.conversation,
    )

    # EVENT, never payload: the live decision log streams to the user BEFORE the
    # output filter runs (core/pipeline.py's ACTIVE_STAGES puts "orchestrator"
    # ahead of "filter"), so a filter-blocked draft's actual text must never sit
    # in `message`/`detail` — those are the only fields the live SSE mapper reads
    # (api/run_state.py::on_log_entry). The real text goes in `full_content`,
    # which the durable CB4 audit mirror (derive_record) reads but the live
    # mapper does not — so a block is still auditable without ever reaching the
    # client on the path the filter was supposed to gate.
    await ports.log.emit(
        DecisionLogEntry(kind="answer", message="answer drafted", full_content=answer.answer_text)
    )
    return OrchestratorResponse(
        text=_resolve_response_text(answer, ctx),
        presentation=answer.presentation,
        message=ctx.assistant_message or "",
        confidence=answer.confidence,
        finding_refs=[f.ref for f in ctx.expert_findings],
    )


def _resolve_response_text(answer: OrchestratorAnswer, ctx: VrakshaContext) -> str:
    """Return filter input selected only by explicit presentation intent.

    Chat always keeps the model's `answer_text`, including when tool work produced
    a separate file. Reports may replace it with a referenced full artifact that
    never transited the orchestrator's context.
    """
    if answer.presentation == "report" and answer.deliverable_ref:
        for finding in ctx.expert_findings:
            if finding.ref == answer.deliverable_ref and finding.full_content:
                return finding.full_content
    return answer.answer_text


async def _sync_mission_state(ports: Ports, ctx: VrakshaContext):
    """Mission-engine loop-wiring (ratified 2026-07-25) — the read-first check, every
    turn: re-reads the graph for an active mission bound to THIS session
    (mission_id := session_id, §1 of the ratified design — a targeted read, no scan,
    no schema change), never trusted from a carried-over ctx. Sets ctx.mission_id
    when one is found and non-terminal — the exact line backend's budget anchor
    reads fresh, per-call (§4: never a ContextVar mirror set once and assumed to
    survive concurrent tool execution). Clears it back to "" when no mission is
    active or it has concluded, so an ordinary turn is never mistaken for a
    mission-bound one. `ports.graph is None` (missions unavailable in this Ports
    instance) degrades to the same "no mission" no-op, matching awareness/batches."""
    if ports.graph is None:
        ctx.mission_id = ""
        return None
    from foundation import GraphScope

    from .mission import MissionStatus
    from .mission_operate import read_mission_state

    scope = GraphScope(user_id=ctx.user_id)
    mission = await read_mission_state(ports.graph, scope, ctx.session_id)
    if mission is None or mission.status in (MissionStatus.DONE, MissionStatus.FAILED, MissionStatus.USER_ENDED):
        ctx.mission_id = ""
        return None
    ctx.mission_id = mission.mission_id
    return mission


def _with_mission_context(user_prompt: str, mission) -> str:
    """Folds the active mission's state into this turn's own task prompt — internal
    context, same "fold into the prompt" shape batches.py's _with_awareness_context
    already uses. A concluded/absent mission (mission is None) changes nothing, so an
    ordinary turn behaves identically to today."""
    if mission is None:
        return user_prompt
    criteria = "\n".join(f"- {c.description}" for c in mission.criteria)
    tasks = "\n".join(
        f"- {t.task_id} ({t.status.value if t.status else 'active'}): {t.summary}" for t in mission.tasks
    ) or "(no tasks yet)"
    section = (
        f"You are working an ACTIVE MISSION (status: {mission.status.value}).\n"
        f"Success criteria:\n{criteria}\n\nTasks so far:\n{tasks}\n\n"
        "Use advance_mission to record task outcomes / propose new tasks / submit "
        "completion_verdicts once every criterion is genuinely met. Use end_mission "
        "only to abort without claiming success."
    )
    return f"{user_prompt}\n\n---\n{section}"
