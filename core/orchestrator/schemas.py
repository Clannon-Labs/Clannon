"""
Orchestrator-internal contracts.

These are the structured shapes the orchestrator uses inside its own layer: the
advisor's per-turn decision, the expert request/summary/findings split, the tool
request, and the decision-log entry. They are Pydantic models so the advisor's
output is schema-validated by the framework adapter.

Cross-stage shapes (OrchestratorResponse, memory contracts) live in
foundation.contracts — not here — because other layers consume them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- advisor input/output ---------------------------------------------------

class ExpertRequest(BaseModel):
    """A request to run one expert, addressed by its domain-qualified key."""
    key: str
    task: str


class ToolRequest(BaseModel):
    """A request to invoke one tool, addressed by its domain-qualified key."""
    key: str
    arguments: dict[str, Any] = Field(default_factory=dict)


DecisionKind = Literal["answer", "spawn_experts", "call_tool", "need_more"]


class OrchestratorDecision(BaseModel):
    """
    One advisor decision per turn. The model only PROPOSES this; Vraksha code
    executes it (permissions, routing, dispatch, logging).
    """
    kind: DecisionKind
    rationale: str = ""
    answer_text: str | None = None
    experts: list[ExpertRequest] = Field(default_factory=list)
    tool: ToolRequest | None = None
    confidence: float = 0.0


# --- expert two-output split ------------------------------------------------

class ExpertSummary(BaseModel):
    """
    Brief summary returned to the orchestrator. The orchestrator only ever sees
    this, never the full findings (keeps its context lean).
    """
    expert: str
    summary: str
    confidence: float = 0.0
    finding_ref: str            # key into ctx.expert_findings for the full content


class ExpertFindings(BaseModel):
    """Full expert output, buffered in ctx.expert_findings for the output filter."""
    expert: str
    ref: str
    full_content: str
    citations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExpertOutput(BaseModel):
    """
    What an expert agent returns. The handler splits it into the brief
    ExpertSummary (to the orchestrator) and the full ExpertFindings (to ctx).
    """
    summary: str
    full_content: str
    citations: list[str] = Field(default_factory=list)
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
