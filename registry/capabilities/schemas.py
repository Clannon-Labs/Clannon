"""
Capability invocation contracts: how a tool/expert is addressed and called, and
what it returns. These are the shared vocabulary of the capability layer —
emitted by the orchestrator's decision, consumed by the handler engines, and
returned by the impls. There is no free-form text: a capability is always called
with `arguments` validated against its declared input_schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    """A request to invoke one tool, addressed by its domain-qualified key."""
    key: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExpertRequest(BaseModel):
    """
    A request to run one expert, addressed by its domain-qualified key.

    `arguments` is structured input validated against the expert's input_schema
    (e.g. {"prompt": "..."}) — never free-form text. The expert is exposed to the
    orchestrator as a native tool whose parameters ARE this schema.
    """
    key: str
    arguments: dict[str, Any] = Field(default_factory=dict)


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
