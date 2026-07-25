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
    artifacts: list[str] = Field(
        default_factory=list,
        description="Workspace-relative paths of files to deliver as output artifacts "
        "(e.g. a generated report or code file). The handler copies these out of the "
        "workspace into durable storage before it is torn down. Empty if nothing to deliver.",
    )


class SpawnBatchArgs(BaseModel):
    """The central orchestrator's `spawn_batch` native tool arguments — ONE tool,
    not one wrapper per batch (unlike experts/tools, which get a wrapper each)."""
    batch_key: str
    task: str


class BatchSummary(BaseModel):
    """
    Brief summary returned to the central orchestrator after a batch's scoped
    run — the two-output split, one tier up from ExpertSummary. `summary` is a
    bounded excerpt of the batch's own answer_text (see BatchHandler's cap
    constant); the full text lives in the matching BatchFindings.
    """
    batch: str
    summary: str
    confidence: float = 0.0
    finding_ref: str            # key into ctx.batch_findings for the full content


class BatchFindings(BaseModel):
    """Full batch output, buffered in ctx.batch_findings for the output filter —
    the batch's own answer_text in full (its constituent experts' full output is
    already buffered separately in ctx.expert_findings, since a batch shares its
    caller's ctx; this holds the batch-level synthesis on top of that, not a
    duplicate of it)."""
    batch: str
    ref: str
    full_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Mission Engine native tools (ratified 2026-07-25, mission-engine-loop-wiring-design) ---

class StartMissionArgs(BaseModel):
    """The central orchestrator's `start_mission` native tool arguments. No id
    field — mission_id is server-minted (session_id, identity-set-once), never
    model-supplied."""
    intent: str
    success_criteria: list[str] = Field(default_factory=list)


class NewTaskArg(BaseModel):
    """One task the model proposes this turn (mirrors mission_operate.NewTask,
    as a model-facing arg — required_permission is a plain PermissionLevel
    string so pydantic-ai can introspect it directly)."""
    task_id: str
    summary: str
    blocks: list[str] = Field(default_factory=list)
    feeds: list[str] = Field(default_factory=list)
    supersedes: str = ""
    required_permission: str = "read"


class TaskTransitionArg(BaseModel):
    """One already-existing task's terminal outcome this turn (mirrors
    mission_operate.TaskTransition). status is one of "done"/"failed"/"superseded"."""
    task_id: str
    status: str
    summary: str
    evidence: str = ""


class CriterionVerdictArg(BaseModel):
    """One success criterion's judged outcome this turn (mirrors
    mission.CriterionVerdict) — only meaningful when the model believes the
    mission is complete; empty completion_verdicts on AdvanceMissionArgs means
    "just advance tasks, not proposing completion yet"."""
    description: str
    met: bool
    evidence: str = ""


class AdvanceMissionArgs(BaseModel):
    """The central orchestrator's `advance_mission` native tool arguments — ONE
    tool bundling one turn's worth of mission_operate.OperateStepTurn (new
    tasks, terminal transitions, and an optional completion judgment)."""
    new_tasks: list[NewTaskArg] = Field(default_factory=list)
    transitions: list[TaskTransitionArg] = Field(default_factory=list)
    completion_verdicts: list[CriterionVerdictArg] = Field(default_factory=list)


class EndMissionArgs(BaseModel):
    """The central orchestrator's `end_mission` native tool arguments — a direct
    terminal transition (USER_ENDED), bypassing the completion-judgment gate."""
    reason: str
