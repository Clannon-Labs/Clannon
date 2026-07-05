"""
Decision-log sink — the loop streams structured entries here as it works.

Minimal at the checkpoint: emit() appends to ctx.decision_log, which the delivery
layer reads to show the user what the orchestrator did and why. The
DecisionLogSink Protocol (ports.py) is the seam — a queue/SSE-backed sink for
live concurrent streaming drops in here later with no change to the loop.

`derive_record()` is CB4's emit-side contract: a pure, best-effort projection of
one live entry into a durable `DecisionRecord`, for a (future) persistence sink
to call alongside this one. It never replaces or changes the live path above.
"""

from __future__ import annotations

import time

from foundation import VrakshaContext

from ..schemas import DecisionLogEntry, DecisionLogKind, DecisionRecord


class CtxDecisionLog:
    """Appends decision-log entries to the request context."""

    def __init__(self, ctx: VrakshaContext) -> None:
        self._ctx = ctx

    async def emit(self, entry: DecisionLogEntry) -> None:
        self._ctx.decision_log.append(entry)


# Kinds that represent an actual model DECISION, not narration. "message" is
# commentary ABOUT a decision (consumed as `reasoning` input below), not a decision
# itself. "warning" is a system degradation fallback, not a model decision — left
# out of v1 (ratified default); an easy toggle if a later audit-mirror use case
# wants degradation events too.
_DECISION_KINDS: frozenset[DecisionLogKind] = frozenset({"tool_call", "answer"})


def derive_record(entry: DecisionLogEntry, ctx: VrakshaContext) -> DecisionRecord | None:
    """Pure, best-effort derivation of a durable CB4 record from a live decision-log
    entry. Returns None for entries that aren't decision points (system/
    conversational narration). Never fabricates data the loop doesn't have:
    `reasoning` is populated ONLY from an actual preceding `say()` message, and
    `tradeoffs` is not attempted at all (see `DecisionRecord`'s docstring for why).

    Safe to call either as each entry is emitted (the intended use — alongside the
    existing live emit, `CtxDecisionLog.emit` / `ports.log.emit`) or after the fact
    over an already-populated `ctx.decision_log` — the reasoning scan is bounded by
    `entry`'s own position, so a later entry already present in the log is never
    mistaken for "before" this one. Never replaces or changes the live emit path."""
    if entry.kind not in _DECISION_KINDS:
        return None

    if entry.kind == "tool_call":
        tool = entry.detail.get("tool")
        participants = [str(tool)] if tool else []
    elif entry.kind == "answer":
        # the full cast for the WHOLE turn, not just this entry — ctx already
        # tracks this authoritatively, no need to accumulate it live
        participants = sorted(
            {c.expert_name for c in ctx.expert_calls} | {c.tool_name for c in ctx.tool_calls}
        )
    else:
        participants = []

    # Reasoning: best-effort scan for the most recent say() strictly BEFORE this
    # entry's own position in the log — identity-based (`is`, never `==`), since
    # two entries can carry identical kind/message/detail and pydantic's default
    # equality would then find the wrong position. Bounding by position (not just
    # "skip this one instance") also makes this correct regardless of whether the
    # caller derives strictly in emission order or has already appended later
    # entries first — it never looks past where this entry actually sits.
    boundary = len(ctx.decision_log)
    for i, e in enumerate(ctx.decision_log):
        if e is entry:
            boundary = i
            break
    reasoning = ""
    for prior in reversed(ctx.decision_log[:boundary]):
        if prior.kind == "message":
            reasoning = prior.message
            break
        if prior.kind in _DECISION_KINDS:
            break   # stop at the last decision point — a message further back
                    # belongs to a DIFFERENT decision, don't misattribute it

    return DecisionRecord(
        decision=entry.message,
        participants=participants,
        reasoning=reasoning,
        ts=time.time(),
        turn=entry.turn,
        kind=entry.kind,
    )
