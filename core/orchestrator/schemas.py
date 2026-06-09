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
    """
    answer_text: str
    confidence: float = 0.0


# --- decision log -----------------------------------------------------------

DecisionLogKind = Literal[
    "hydration", "route", "expert_spawn", "tool_call",
    "observation", "answer", "warning", "error",
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
