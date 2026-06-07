"""
The orchestrator reasoning loop — UI-agnostic core logic.

Vraksha owns this loop; the model only advises. Each turn:
  1. ask the advisor for a structured decision,
  2. emit it to the decision-log sink,
  3. execute it in Vraksha code (answer / spawn experts / call tool / continue),
  4. feed structured observations back.
Terminate on an `answer`, or force a final answer at the turn cap.

The loop holds no UI or transport logic — any consumer (TUI now, frontend later)
connects through the decision-log sink and the returned OrchestratorResponse.
The whole-loop timeout is applied by the stage (orchestrator.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from foundation import (
    HydrationPackage,
    HydrationRequest,
    MaxRetriesExceededError,
    NormalizedInput,
    OrchestratorResponse,
    VrakshaContext,
    constants,
)

from . import advisor
from .ports import Ports
from .schemas import DecisionLogEntry, OrchestratorDecision

# Names the router can choose from. Empty until real experts exist; the advisor
# may still name experts explicitly (the stub handler will run them).
EXPERT_CANDIDATES: list[str] = []


@dataclass
class LoopState:
    """Working state carried across turns (the advisor is stateless)."""
    request: NormalizedInput
    hydration: HydrationPackage
    observations: list[Any] = field(default_factory=list)
    turn: int = 0


async def run_loop(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> OrchestratorResponse:
    """Run the bounded reasoning loop and return a draft response."""
    hydration = await _hydrate(normalized, ports, ctx)
    state = LoopState(request=normalized, hydration=hydration)

    for turn in range(constants.ORCHESTRATOR_MAX_TURNS):
        state.turn = turn
        decision = await advisor.decide(normalized, hydration, state.observations, turn)
        await ports.log.emit(_decision_entry(decision, turn))

        if decision.kind == "answer":
            return _response(decision, ctx)

        if decision.kind == "spawn_experts":
            await _run_experts(decision, ports, ctx, state, turn)
        elif decision.kind == "call_tool" and decision.tool is not None:
            await _run_tool(decision, ports, ctx, state, turn)
        # "need_more" (or an empty action) just continues to the next turn.

    return await _force_final_answer(normalized, hydration, ports, ctx, state)


async def _hydrate(normalized: NormalizedInput, ports: Ports, ctx: VrakshaContext) -> HydrationPackage:
    """Ask the memory manager (via the port) for context before planning."""
    await ports.log.emit(DecisionLogEntry(kind="hydration", message="requesting memory hydration"))
    hydration = await ports.memory.hydrate(
        HydrationRequest(session_id=ctx.session_id, normalized=normalized)
    )
    if hydration.notes:
        await ports.log.emit(DecisionLogEntry(kind="hydration", message=hydration.notes))
    return hydration


async def _run_experts(decision, ports, ctx, state, turn) -> None:
    chosen = decision.experts or ports.router.route(state.request, EXPERT_CANDIDATES)
    if not chosen:
        state.observations.append("no experts available; answer directly")
        return
    await ports.log.emit(DecisionLogEntry(
        kind="expert_spawn",
        message=f"spawning {len(chosen)} expert(s)",
        turn=turn,
        detail={"experts": [e.name for e in chosen]},
    ))
    summaries = await ports.experts.run_experts(chosen, ctx)
    state.observations.extend(summaries)
    for summary in summaries:
        await ports.log.emit(DecisionLogEntry(
            kind="observation",
            message=f"expert {summary.expert}: {summary.summary}",
            turn=turn,
        ))


async def _run_tool(decision, ports, ctx, state, turn) -> None:
    await ports.log.emit(DecisionLogEntry(
        kind="tool_call",
        message=f"calling tool {decision.tool.name}",
        turn=turn,
        detail={"tool": decision.tool.name},
    ))
    record = await ports.tools.call_tool(decision.tool, ctx)
    outcome = "ok" if record.success else (record.error or "failed")
    state.observations.append(f"tool {record.tool_name}: {outcome}")
    await ports.log.emit(DecisionLogEntry(
        kind="observation",
        message=f"tool {record.tool_name} -> {outcome}",
        turn=turn,
    ))


async def _force_final_answer(normalized, hydration, ports, ctx, state) -> OrchestratorResponse:
    """At the turn cap, demand one final answer; fail closed if none is produced."""
    cap = constants.ORCHESTRATOR_MAX_TURNS
    forced = await advisor.decide(normalized, hydration, state.observations, cap, force_answer=True)
    await ports.log.emit(_decision_entry(forced, cap))
    if forced.kind == "answer" and forced.answer_text:
        return _response(forced, ctx)
    await ports.log.emit(DecisionLogEntry(kind="error", message="turn cap reached without an answer", turn=cap))
    raise MaxRetriesExceededError("orchestrator reached its turn cap without an answer")


def _decision_entry(decision: OrchestratorDecision, turn: int) -> DecisionLogEntry:
    """Render an advisor decision as a decision-log entry."""
    kind = "answer" if decision.kind == "answer" else "route"
    return DecisionLogEntry(
        kind=kind,
        message=decision.rationale or decision.kind,
        turn=turn,
        detail={"action": decision.kind, "confidence": decision.confidence},
    )


def _response(decision: OrchestratorDecision, ctx: VrakshaContext) -> OrchestratorResponse:
    """Build the draft response, linking any buffered expert findings."""
    return OrchestratorResponse(
        text=decision.answer_text or "",
        confidence=decision.confidence,
        metadata={"action": decision.kind},
        finding_refs=[f.ref for f in ctx.expert_findings],
    )
