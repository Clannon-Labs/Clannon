"""
foundation/pillars/context.py

The request-scoped context object for Vraksha.

One VrakshaContext is created at intake for every user turn.
It travels through every stage of the pipeline, accumulating state.
Every stage reads from it and writes to it.

Why this exists:
    Without a context object, stages pass data through function arguments.
    As the pipeline grows, functions end up with 8–12 parameters.
    Worse, when something fails mid-pipeline you have to reconstruct
    what happened by reading logs. With context, you print one object
    and see the full request history.

How to use it:
    Context is created and carried automatically by Flow.
    You never instantiate it directly in stage code.

    1. Flow creates it:
            flow = Flow.new(raw_input, session_id=session.id)
            # flow.ctx is a fresh VrakshaContext

    2. Each stage writes results back via flow.ctx:
            flow.ctx.sanitization = result
            flow.ctx.detected_modalities = result.modalities

    3. Flow updates terminal state automatically when you call
       flow.block() or flow.fail(). Flow.new() sets the initial INTAKE stage.
       Per-stage transitions are represented by Flow.meta.origin and the
       journal. If you need current_stage to track each layer, update it in
       the pipeline wrapper or add explicit Flow support for that mapping.

    4. On failure, inspect the full context:
            logger.error("pipeline failed", **flow.ctx.snapshot())

    Advanced: if you need a context without a Flow (e.g. tests, tooling):
            ctx = VrakshaContext.new(session_id="test-session")

Placeholder types:
    Several fields use placeholder types (marked with # PLACEHOLDER).
    These will be replaced with real Pydantic models as each layer is built.
    Do not remove the placeholders — they document what will go there
    and allow the rest of the pipeline skeleton to be written now.

Sections:
    PipelineStage    — enum of pipeline stages
    ToolCallRecord   — record of one tool invocation
    ExpertCallRecord — record of one expert invocation
    VrakshaContext   — the main context dataclass
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------

class PipelineStage(str, Enum):
    """
    Tracks coarse pipeline state.
    Used for logging, dead letter output, and debugging.
    Flow.new() sets INTAKE.
    Flow.block() sets BLOCKED automatically.
    Flow.fail() sets FAILED automatically.
    """
    CREATED       = "created"
    INTAKE        = "intake"
    SANITIZING    = "sanitizing"
    NORMALIZING   = "normalizing"
    VERIFYING     = "verifying"
    ORCHESTRATING = "orchestrating"
    FILTERING     = "filtering"
    OUTPUT        = "output"
    DONE          = "done"
    BLOCKED       = "blocked"
    FAILED        = "failed"


@dataclass
class ToolCallRecord:
    """
    A record of one tool invocation during the orchestrator's reasoning loop.
    The orchestrator may invoke multiple tools per turn.
    All calls are appended to ctx.tool_calls in order.

    tool_name     — which tool was called
    arguments     — arguments passed to the tool handler (sanitized copy)
    result        — structured JSON result from the sandbox
    success       — whether the tool completed without error
    duration_ms   — wall time for this invocation
    error         — error message if success=False
    span_id       — the Flow span that produced this call
    """
    tool_name:   str
    arguments:   dict[str, Any]
    result:      dict[str, Any] | None = None
    success:     bool                  = False
    duration_ms: float | None          = None
    error:       str | None            = None
    span_id:     str                   = field(default_factory=lambda: uuid4().hex[:8])


@dataclass
class ExpertCallRecord:
    """
    A record of one expert invocation during the orchestrator's reasoning loop.
    The orchestrator may invoke multiple experts per turn, potentially in parallel.
    All calls are appended to ctx.expert_calls in order of completion.

    expert_name    — which expert was invoked
    arguments      — arguments passed to the expert handler
    result         — structured response from the expert
    success        — whether the expert completed without error
    duration_ms    — wall time for this invocation
    error          — error message if success=False
    sub_tool_calls — tool calls the expert made during its own execution
    span_id        — the Flow span that produced this call
    """
    expert_name:    str
    arguments:      dict[str, Any]
    result:         dict[str, Any] | None  = None
    success:        bool                   = False
    duration_ms:    float | None           = None
    error:          str | None             = None
    sub_tool_calls: list[ToolCallRecord]   = field(default_factory=list)
    span_id:        str                    = field(default_factory=lambda: uuid4().hex[:8])


# ---------------------------------------------------------------------------
# VrakshaContext
# ---------------------------------------------------------------------------

@dataclass
class VrakshaContext:
    """
    The single source of truth for one user turn.

    Created automatically by Flow.new(). Carried in flow.ctx.
    Never instantiate directly in stage code — use Flow.

    Fields are grouped by the stage that writes them.
    A field being None means that stage hasn't run yet,
    or was skipped (e.g. no audio in input = audio sanitizer skipped).
    """

    # ------------------------------------------------------------------
    # Identity — set at creation, never change
    # ------------------------------------------------------------------

    trace_id:    str    # matches Flow.meta.trace_id for this request
    created_at:  float  # monotonic clock, for total duration calculation
    session_id:  str    # which session this turn belongs to
    user_id:     str    # set once at the authenticated entry; the sole identity for
                        # downstream memory/tool scoping, never re-derived from content

    # ------------------------------------------------------------------
    # Stage tracking
    # Flow.new(), Flow.block(), and Flow.fail() update this automatically.
    # Flow.next() and Flow.warn() do not currently advance it.
    # ------------------------------------------------------------------

    current_stage: PipelineStage = PipelineStage.CREATED

    # ------------------------------------------------------------------
    # INTAKE
    # Written by: core/intake.py
    # ------------------------------------------------------------------

    raw_input:     Any | None = None   # PLACEHOLDER: will be intake.RawInput
                                       # the raw, unprocessed input exactly as received

    detected_modalities: list[str] = field(default_factory=list)
                                       # which modalities were detected in raw_input
                                       # e.g. ["text", "pdf", "image"]

    # ------------------------------------------------------------------
    # SANITIZATION
    # Written by: security/sanitizers/runner.py
    # One result per modality. None = not present in this input.
    # ------------------------------------------------------------------

    sanitization:  Any | None = None   # PLACEHOLDER: will be sanitizers.SanitizationResult
                                       # aggregate result from all parallel workers

    sanitization_blocked: bool = False
    sanitization_block_reason: str | None = None

    # ------------------------------------------------------------------
    # NORMALIZATION
    # Written by: core/normalizer.py
    # ------------------------------------------------------------------

    normalized_input: Any | None = None  # PLACEHOLDER: will be foundation.NormalizedInput
                                         # structured form of the sanitized input
                                         # this is what the verifier and orchestrator see

    # ------------------------------------------------------------------
    # VERIFICATION
    # Written by: core/verifier/verifier.py
    # ------------------------------------------------------------------

    verifier_result: Any | None = None   # PLACEHOLDER: will be foundation.VerificationResult
                                         # structured JSON from the verifier LLM:
                                         # {dangerous, warn, proceed, ...}

    verifier_blocked: bool = False
    verifier_block_reason: str | None = None

    # ------------------------------------------------------------------
    # ORCHESTRATOR
    # Written by: core/orchestrator.py and handlers/
    # ------------------------------------------------------------------

    tool_calls:    list[ToolCallRecord]   = field(default_factory=list)
    expert_calls:  list[ExpertCallRecord] = field(default_factory=list)

    decision_log:  list[Any] = field(default_factory=list)
                                              # PLACEHOLDER: will be orchestrator.DecisionLogEntry
                                              # audit mirror of the streamed decision log; the
                                              # live stream goes through the decision-log sink

    expert_findings: list[Any] = field(default_factory=list)
                                              # PLACEHOLDER: will be orchestrator.ExpertFindings
                                              # FULL expert findings buffered for the output filter.
                                              # The orchestrator never reads these — it only sees
                                              # brief expert summaries (keeps its context lean)

    orchestrator_response: Any | None = None  # PLACEHOLDER: will be foundation.OrchestratorResponse
                                              # raw response before output filtering

    memory_writes_requested: list[Any] = field(default_factory=list)
                                              # PLACEHOLDER: will be foundation.MemoryWriteProposal
                                              # items the orchestrator flagged for memory

    # ------------------------------------------------------------------
    # OUTPUT FILTER
    # Written by: security/filter/filter.py
    # ------------------------------------------------------------------

    filter_result: Any | None = None     # PLACEHOLDER: will be filter.FilterResult
                                         # structured JSON from the filter LLM

    filter_blocked: bool = False
    filter_block_reason: str | None = None
    filter_retry_count: int = 0          # how many times filter rejected and retried

    # ------------------------------------------------------------------
    # FINAL OUTPUT
    # Written by: core/output.py
    # ------------------------------------------------------------------

    final_response: Any | None = None    # PLACEHOLDER: will be output.FinalResponse
                                         # what the user actually receives

    # ------------------------------------------------------------------
    # Terminal state
    # Set automatically by Flow.block() and Flow.fail().
    # Do not set these directly in stage code.
    # blocked=True means user gets a system-generated block message, no LLM output.
    # failed=True means something broke, user gets a generic error message.
    # ------------------------------------------------------------------

    blocked:       bool        = False
    block_reason:  str | None  = None   # internal only, never shown to user verbatim
    failed:        bool        = False
    failure_error: str | None  = None   # internal only

    # ------------------------------------------------------------------
    # Timing — filled progressively as stages complete
    # ------------------------------------------------------------------

    stage_durations: dict[str, float] = field(default_factory=dict)
                                         # stage_name → duration_ms
                                         # filled by each stage via ctx.record_duration()

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    @classmethod
    def new(
        cls,
        session_id: str,
        user_id: str = "local-user",
        trace_id: str | None = None,
    ) -> "VrakshaContext":
        """
        Create a fresh context for a new user turn.
        trace_id is generated here and stays fixed for the request lifetime.
        user_id defaults to the local single-user id; the authenticated entry
        point passes the real one.

        In normal pipeline code, you never call this directly —
        Flow.new() calls it and attaches the result to flow.ctx.

        Call directly only in tests or tooling that needs a context
        without a full Flow.
        """
        return cls(
            trace_id=trace_id or uuid4().hex,
            created_at=time.monotonic(),
            session_id=session_id,
            user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # Called by Flow internally. Available for direct use in tests/tooling.
    # ------------------------------------------------------------------

    def advance(self, stage: PipelineStage) -> None:
        """
        Move to the next pipeline stage.
        Use this from a pipeline wrapper if you need explicit stage tracking.
        """
        self.current_stage = stage

    def record_duration(self, stage: str, duration_ms: float) -> None:
        """
        Record how long a stage took.
        Flow journal entries already carry transition durations. Use this only
        if you also want a stage-name to duration map on the context.
        """
        self.stage_durations[stage] = duration_ms

    def mark_blocked(self, reason: str) -> None:
        """
        Mark this request as blocked.
        Called automatically by Flow.block() — do not call manually in stage code.
        reason is internal only — never pass it directly to user output.
        """
        self.blocked = True
        self.block_reason = reason
        self.current_stage = PipelineStage.BLOCKED

    def mark_failed(self, error: str) -> None:
        """
        Mark this request as failed due to an infrastructure/code error.
        Called automatically by Flow.fail() — do not call manually in stage code.
        """
        self.failed = True
        self.failure_error = error
        self.current_stage = PipelineStage.FAILED

    @property
    def total_duration_ms(self) -> float:
        """Wall time from context creation to now, in milliseconds."""
        return (time.monotonic() - self.created_at) * 1000

    @property
    def should_stop(self) -> bool:
        """True if the pipeline must not proceed to the next stage."""
        return self.blocked or self.failed

    def snapshot(self) -> dict[str, Any]:
        """
        Minimal dict for structured logging and dead letter output.
        Safe to log — does not include raw_input or other sensitive payload.

        Usage:
            logger.error("pipeline failed", **flow.ctx.snapshot())
        """
        return {
            "trace_id":         self.trace_id,
            "session_id":       self.session_id,
            "user_id":          self.user_id,
            "stage":            self.current_stage.value,
            "blocked":          self.blocked,
            "block_reason":     self.block_reason,
            "failed":           self.failed,
            "failure_error":    self.failure_error,
            "modalities":       self.detected_modalities,
            "tool_calls":       len(self.tool_calls),
            "expert_calls":     len(self.expert_calls),
            "decision_log":     len(self.decision_log),
            "expert_findings":  len(self.expert_findings),
            "filter_retries":   self.filter_retry_count,
            "stage_durations":  self.stage_durations,
            "total_ms":         round(self.total_duration_ms, 2),
        }

    def __repr__(self) -> str:
        return (
            f"VrakshaContext("
            f"trace={self.trace_id[:8]}..., "
            f"stage={self.current_stage.value}, "
            f"blocked={self.blocked}, "
            f"failed={self.failed}"
            f")"
        )
