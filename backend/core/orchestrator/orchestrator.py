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


def _is_substantive_turn(normalized, response, ctx) -> bool:
    """Worth recording to episodic memory / distilling from: the turn did real work
    (experts or tools ran) or exchanged something non-trivial. A bare greeting or a
    one-word reply is NOT substantive, so episodic doesn't fill up with noise."""
    if getattr(ctx, "expert_findings", None) or getattr(ctx, "tool_calls", None):
        return True
    task = (getattr(normalized, "content", "") or "").strip()
    answer = (getattr(response, "text", "") or "").strip()
    return len(task) >= 40 or len(answer) >= 200


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

        # Memory writes for this turn are DEFERRED to AFTER the output filter accepts
        # the draft (core.pipeline calls `persist_turn_memory` on the delivered path),
        # so a draft the filter BLOCKS never seeds memory — the invariant now holds on
        # the initial pass, not just the revision loop. See `persist_turn_memory` below
        # and docs/ARCHITECTURE.md §5.3.
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


async def persist_turn_memory(ctx) -> None:
    """Persist this turn's memory — POST-FILTER, on the DELIVERED path only.

    Called by `core.pipeline` ONLY after the output filter has ACCEPTED the draft and it
    is being delivered, so a draft the filter blocks never seeds memory (the
    "rejected drafts never touch memory" invariant now holds on the INITIAL pass, not
    just the bounded revision loop). Experts/orchestrator only PROPOSE; the manager owns
    persistence. Best-effort: the answer is already delivered, so a memory fault must
    never turn a successful turn into a failed one.

      - EPISODIC: a recollection of the turn, built from the FINAL delivered answer (a
        revised draft records what the user actually received, not the blocked draft),
        and only when the turn is SUBSTANTIVE — a trivial exchange ("hey" -> "hello")
        has nothing worth recalling cross-session and would just pollute episodic.
      - the `remember` tool's writes (facts/preferences the orchestrator chose to keep,
        or the user asked it to) are already on ctx.memory_writes_requested; they
        persist together with the episodic note. On a blocked turn this function never
        runs, so those proposals are never written either.
    """
    response = ctx.orchestrator_response
    if response is None:
        return
    normalized = ctx.normalized_input
    task_content = getattr(normalized, "content", "") or ""
    ports = build_default_ports(ctx)
    substantive = _is_substantive_turn(normalized, response, ctx)
    try:
        if substantive:
            ctx.memory_writes_requested.append(
                MemoryWriteProposal(
                    store=MemoryStore.EPISODIC,
                    content=f"task: {task_content[:200]} | answer: {response.text[:500]}",
                    rationale="turn outcome",
                    confidence=response.confidence,
                )
            )
        if ctx.memory_writes_requested:
            # the Manager returns only what it ACTUALLY persisted; the delivered-path
            # /memory view surfaces THIS set, so a proposal the policy dropped (low
            # confidence / store down) never shows as a phantom write.
            ctx.memory_writes_persisted = await ports.memory.record_write_proposals(
                ctx.user_id, ctx.session_id, ctx.memory_writes_requested
            )
    except Exception as exc:  # noqa: BLE001 — answer already delivered; memory is best-effort
        log.warning("memory write proposals dropped: %s", exc)

    # the memory agent distils semantic facts + procedural patterns from the turn (its
    # own LLM call, behind the port). Only on substantive turns, and off the critical
    # path: the answer is already delivered, so distillation runs in the background.
    if substantive:
        _spawn_background(_learn(
            ports, ctx.user_id, ctx.session_id,
            task=task_content,
            answer=response.text,
            findings=[getattr(f, "full_content", "") for f in ctx.expert_findings],
        ))
