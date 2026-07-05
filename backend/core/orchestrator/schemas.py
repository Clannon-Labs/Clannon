"""
Orchestrator-internal contracts: the agent's final answer and the decision-log
entry. These are the orchestrator's own vocabulary.

The orchestrator runs as a native tool-driving agent (capabilities are real
tools), so there is no structured per-turn "decision" anymore — just the final
`OrchestratorAnswer`. Capability invocation contracts live with the capability
layer in registry.capabilities; cross-stage shapes (OrchestratorResponse, memory
contracts) live in foundation.contracts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- agent output -----------------------------------------------------------

class OrchestratorAnswer(BaseModel):
    """
    The orchestrator agent's final structured output for a turn — produced after
    it has used whatever tools/experts it needed. The loop maps this to the
    cross-stage OrchestratorResponse (adding finding refs from ctx).

    `deliverable_ref` lets a full expert artifact (e.g. a synthesized report) BE
    the response without transiting the orchestrator's context: when set, the
    loop swaps that finding's full content in as the response text and
    `answer_text` serves as the lean summary for the decision log.
    """
    answer_text: str
    confidence: float = 0.0
    deliverable_ref: str = ""


# --- decision log -----------------------------------------------------------

DecisionLogKind = Literal[
    "hydration", "route", "expert_spawn", "tool_call",
    "observation", "answer", "warning", "error",
    "message",   # the orchestrator's conversational voice — streamed live to the user as
                 # a `message_delta`, distinct from the structured decision ticks above
]


class DecisionLogEntry(BaseModel):
    """
    One structured decision-log entry streamed to the user in real time. This is
    NOT prose — it is what the orchestrator is doing and why.
    """
    kind: DecisionLogKind
    message: str
    turn: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


# --- CB4: the durable decision-record contract ------------------------------

class DecisionRecord(BaseModel):
    """
    A durable, queryable record of ONE decision point in a turn — the CB4
    audit-mirror contract (institutional decision memory). Derived from a
    `DecisionLogEntry` via `derive_record()` (utils/decision_log.py); NOT every
    entry produces one — system/conversational narration derives to `None`.

    Lean by design: every field is derivable from what the loop already knows.
    No field requires a new LLM call. `tradeoffs` (discrete alternatives + risks
    the orchestrator considered and rejected) is DELIBERATELY ABSENT — today's
    native tool-calling gives the model no channel to report that; capturing it
    needs a prompt/schema decision (e.g. asking the model to narrate
    alternatives via `say()`), not a log-schema change. Flagged, not assumed.

    This is a DERIVED PROJECTION of the live log, not a parallel path —
    `DecisionLogEntry` stays the single source of truth; a persistent sink calls
    `derive_record()` alongside the existing live emit, purely additively.
    """
    decision: str                                            # what was decided/done
    participants: list[str] = Field(default_factory=list)    # tool/expert key(s) involved
    reasoning: str = ""                                       # best-effort: preceding say() text, if any — never fabricated
    ts: float                                                 # wall-clock (time.time()) at derivation
    turn: int = 0                                             # mirrors DecisionLogEntry.turn
    kind: DecisionLogKind                                     # which decision-log kind this derived from
