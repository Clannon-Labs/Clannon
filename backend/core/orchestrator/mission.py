"""
Mission Engine — lifecycle state + fail-closed decision logic. UNGATED PORTION
ONLY (design ratified 2026-07-05,
proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md).

A mission is a persistent, resumable state machine living as a subgraph in the
knowledge web (docs/ARCHITECTURE.md §6.1) — MISSION/TASK nodes and dependency
edges through GraphPort, not a chat transcript. This module holds only the
parts of that design that touch neither GraphPort nor the not-yet-placed
NodeLabel/EdgeLabel values:

    - the lifecycle state set (§3)
    - the criterion/outcome shapes judgment logic is built against
    - two fail-closed decision functions: the proposed_complete -> done gate
      (§4) and the mission budget pre-check (§7)

`TaskOutcome` is a PROJECTED type, not a raw GraphNode — deliberately, so this
module stays valid regardless of which GraphPort node-mutation variant memory
confirms (the design's one open seam question). The operate-step that actually
reads/writes MISSION and TASK nodes is NOT here: it's gated on that answer plus
backend placing the labels. Build the functions the operate-step will call, not
the calls themselves — this module is the ungated half of the deliverable, not
a stand-in for the gated half.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from foundation import TokenBudget


# --- lifecycle state (§3) ----------------------------------------------------

class MissionStatus(str, Enum):
    """
    docs/ARCHITECTURE.md §6.1: active -> blocked -> active -> ... ->
    proposed_complete -> done, plus two safety states (budget_paused,
    awaiting_approval) entered from ACTIVE and returned to it once cleared.
    A mission concludes via DONE, FAILED, or USER_ENDED — nothing else ends it.
    """
    ACTIVE = "active"
    BLOCKED = "blocked"
    PROPOSED_COMPLETE = "proposed_complete"
    DONE = "done"
    FAILED = "failed"
    USER_ENDED = "user_ended"
    BUDGET_PAUSED = "budget_paused"
    AWAITING_APPROVAL = "awaiting_approval"


# --- success criteria + task outcomes (§4) -----------------------------------

class Criterion(BaseModel):
    """One success criterion. Written once at mission creation as part of the
    MISSION node's write-once anchor (§1) and never mutated — re-read from the
    graph every operate-step rather than trusted from working context, which is
    what makes drift across compactions/restarts structurally impossible."""
    description: str


class TaskStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class TaskOutcome(BaseModel):
    """A terminal task's outcome, projected out of the graph for judgment
    purposes. Deliberately not a raw GraphNode: the judgment logic below stays
    correct under either §1 node-mutation variant memory confirms, and under
    whatever §2 bulk-read mechanism ends up fetching these."""
    task_id: str
    summary: str
    status: TaskStatus
    evidence: str = ""


class CriterionVerdict(BaseModel):
    """One criterion's judged outcome. `description` is carried through for the
    decision log / audit trail only — `evaluate_completion` never string-matches
    on it (see that function's docstring for why)."""
    description: str
    met: bool
    evidence: str = ""


class CompletionJudgment(BaseModel):
    """The judge's structured output: an evidence-check of the stored criteria
    against terminal task outcomes — the mission analogue of the output filter
    (§4), "done means genuinely done, never vibes." Produced by whichever
    wiring invokes the judge (gated, not built here); this module only
    consumes the result."""
    criteria_verdicts: list[CriterionVerdict] = Field(default_factory=list)
    reasoning: str = ""


def evaluate_completion(criteria: list[Criterion], judgment: CompletionJudgment) -> MissionStatus:
    """
    Fail-closed gate for proposed_complete -> done (§4). Never trusts a
    top-level "is this done" claim — only ever checks per-criterion `met`
    flags, correlated to `criteria` BY POSITION (not by searching for a
    matching `description` string), with the claimed `description` at each
    position then checked for equality as an INTEGRITY check on that
    correlation — catching a judgment that reordered or dropped a criterion,
    which raw positional trust would silently misattribute. Any length
    mismatch, any position where the description doesn't match what was
    asked, or any unmet criterion holds the mission at PROPOSED_COMPLETE — it
    never auto-advances on an incomplete or malformed judgment. A false
    negative here just costs another turn's re-judgment; a false positive
    would end the mission wrong, so every ambiguity resolves toward staying
    open.
    """
    if len(judgment.criteria_verdicts) != len(criteria):
        return MissionStatus.PROPOSED_COMPLETE
    for criterion, verdict in zip(criteria, judgment.criteria_verdicts):
        if verdict.description != criterion.description or not verdict.met:
            return MissionStatus.PROPOSED_COMPLETE
    return MissionStatus.DONE


# --- budget pre-check (§7) ----------------------------------------------------

def budget_is_sufficient(budget: TokenBudget, estimate: int) -> bool:
    """
    The mission-level pre-check consuming BudgetPort.remaining() (§7) —
    proactive and coarse, checked BEFORE a turn's model call is attempted, so
    an insufficient mission ceiling transitions ACTIVE -> BUDGET_PAUSED without
    ever starting the call. Distinct from BudgetExhausted
    (foundation.vocab.errors), the reactive per-call backstop enforced below
    the orchestrator (ADR-0004) — this check can pass and that one can still
    fire; they are complementary layers, not redundant ones.
    """
    if budget.mission_remaining is not None and budget.mission_remaining < estimate:
        return False
    return budget.user_remaining >= estimate
