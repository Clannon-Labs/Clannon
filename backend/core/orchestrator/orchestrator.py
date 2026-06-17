"""
Orchestrator stage — the layer's entry point.

A Flow stage like the others (`async def run(flow) -> Flow`). It builds the
default ports, runs the bounded reasoning loop under the orchestrator timeout,
stores the draft response and proposed memory writes on the context, and hands
off. The orchestrator never content-blocks (the verifier and the output filter
own that); a timeout, provider rate-limit storm, or loop fault degrades
gracefully (utils/recovery) to an honest, grounded answer rather than a blank
failure — the user never gets nothing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from foundation import (
    Flow,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
    Origin,
    PipelineStage,
    constants,
)

from .loop import run_loop
from .schemas import DecisionLogEntry
from .utils.recovery import build_degraded_response, classify_failure, degraded_reason
from .utils.wiring import build_default_ports

log = logging.getLogger(__name__)

# Strong refs to in-flight background tasks (memory distillation). Without this the
# event loop only holds a weak ref and the task can be GC'd mid-flight; the
# done-callback discards it when finished.
_BACKGROUND: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    """Fire a best-effort coroutine off the critical path and keep a strong ref."""
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:  # no running loop (shouldn't happen in the pipeline) — skip
        return
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


async def _learn(ports, user_id: str, session_id: str, *, task: str, answer: str, findings: list[str]) -> None:
    """Background distillation wrapper: a learning fault must never surface."""
    try:
        await ports.memory.learn(user_id, session_id, task=task, answer=answer, findings=findings)
    except Exception as exc:  # noqa: BLE001 — best-effort, off the hot path
        log.warning("memory learning dropped: %s", exc)


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Pipeline entry point for orchestration."""
    started = time.monotonic()
    try:
        # coerce so the normalizer (and the whole input gate) is optional: a raw
        # payload becomes a valid NormalizedInput here. No-op when an upstream
        # stage already produced one.
        normalized = NormalizedInput.coerce(await flow.load())
        flow.ctx.advance(PipelineStage.ORCHESTRATING)
        ports = build_default_ports(flow.ctx)

        response = await asyncio.wait_for(
            run_loop(normalized, ports, flow.ctx),
            timeout=constants.ORCHESTRATOR_TIMEOUT_S,
        )

        flow.ctx.orchestrator_response = response

        # Propose an episodic memory of this turn (experts/orchestrator only PROPOSE;
        # the manager owns persistence). Minimal: remember the request and answer.
        # Best-effort: the answer is already produced — a memory fault must never
        # turn a successful turn into a failed one.
        try:
            flow.ctx.memory_writes_requested.append(
                MemoryWriteProposal(
                    store=MemoryStore.EPISODIC,
                    content=f"task: {(normalized.content or '')[:200]} | answer: {response.text[:500]}",
                    rationale="turn outcome",
                    confidence=response.confidence,
                )
            )
            await ports.memory.record_write_proposals(
                flow.ctx.user_id, flow.ctx.session_id, flow.ctx.memory_writes_requested
            )
        except Exception as exc:
            log.warning("memory write proposals dropped: %s", exc)

        # the memory agent distils semantic facts + procedural patterns from the
        # turn (its own LLM call, behind the port). Only on substantive turns — a
        # quick conversational reply has nothing durable to learn. Best-effort AND
        # off the critical path: the answer already exists, so the distillation
        # (a second LLM call) runs in the background and the stage returns
        # immediately, instead of making the user wait on it before delivery.
        if flow.ctx.expert_findings or len(response.text) >= 240:
            _spawn_background(_learn(
                ports, flow.ctx.user_id, flow.ctx.session_id,
                task=normalized.content or "",
                answer=response.text,
                findings=[getattr(f, "full_content", "") for f in flow.ctx.expert_findings],
            ))

        return flow.next(response, Origin.ORCHESTRATOR, started)

    except Exception as exc:
        # Graceful degradation: a timeout, a provider rate-limit storm, or an
        # unexpected fault must never hand the user a blank failure. Salvage an
        # honest, grounded answer from whatever the run already gathered (LLM-free
        # — another model call would only fail again under rate limits) and let it
        # flow on through the filter → delivery like any answer.
        kind = classify_failure(exc)
        log.warning("orchestrator degraded (%s): %s", kind, exc)
        flow.ctx.decision_log.append(
            DecisionLogEntry(kind="warning", message=f"answering in degraded mode: {degraded_reason(kind)}")
        )
        degraded = build_degraded_response(flow.ctx, kind)
        flow.ctx.orchestrator_response = degraded
        return flow.next(degraded, Origin.ORCHESTRATOR, started)
