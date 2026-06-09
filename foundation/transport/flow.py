"""
foundation/flow.py

The Flow object — the single transport type for Vraksha.

Every stage boundary in the pipeline takes a Flow and returns a Flow.
Nothing else crosses stage boundaries.

Design lineage:
    Railway Oriented Programming (Rust/Elixir)
        → automatic error propagation via .then(), stages never check errors manually
    OpenTelemetry Baggage + Carrier pattern
        → inject/extract interface, controlled access, sensitive data never leaks
    Google ADK Handle pattern
        → payload is a lightweight descriptor, not inline data
          stages load() only when they actually need raw bytes
    Google ADK InvocationContext flavors
        → scoped access per stage, least privilege at the type level
    Transition journal (Vraksha-original)
        → every state change is recorded automatically, zero developer effort
          observability is not instrumented — it is structural

The one import rule:
    from foundation import Flow
    That is the only import a stage ever needs for transport.

Usage — creating:
    flow = Flow.new(raw_input, session_id="abc")

Usage — pipeline (preferred):
    result = await (
        Flow.new(raw_input, session_id)
        .then(intake.process)
        .then(sanitizer.run)
        .then(normalizer.run)
        .then(verifier.verify)
        .then(orchestrator.run)
        .then(output_filter.run)
        .then(output.send)
    )

Usage — manual (when you need fine control):
    flow = await sanitizer.run(flow)
    if flow.should_stop:
        return flow

Usage — inside a stage:
    async def run(flow: Flow) -> Flow:
        started = time.monotonic()
        raw = await flow.load()                  # load payload only when needed
        result = await do_work(raw)
        return flow.next(result, Origin.SANITIZER, started)

Usage — blocking:
    return flow.block(BlockReason.MALICIOUS_CONTENT, ThreatLevel.HIGH, Origin.SANITIZER)

Usage — failing (infrastructure fault):
    return flow.fail(SandboxError("timeout", cause=e), Origin.TOOL_HANDLER)

Usage — warning (pass but flag):
    return flow.warn("low confidence", ThreatLevel.LOW, Origin.VERIFIER)

Usage — logging (always use .summary(), never log flow directly):
    logger.warning("blocked", **flow.summary())

Usage — debugging (full journal of every state change):
    for entry in flow.journal:
        print(entry)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar
from uuid import uuid4

from .pillars.context import VrakshaContext, PipelineStage
from .pillars.errors import VrakshaError
from .pillars.types import BlockReason, ThreatLevel, Origin
from .pillars.transport import Status, Meta
from . import constants

T = TypeVar("T")
U = TypeVar("U")


# ---------------------------------------------------------------------------
# Payload handle
# Payload is never carried inline. A handle carries a descriptor and
# a loader function. The stage calls flow.load() only when it needs
# the actual data. After .next() the handle is replaced — old data
# is never referenced again, allowing GC to free it immediately.
# ---------------------------------------------------------------------------

@dataclass
class PayloadHandle(Generic[T]):
    """
    A lightweight descriptor for the actual payload data.

    descriptor  — minimal metadata about the payload: type, size, checksum.
                  always safe to log. never contains raw data.
    _loader     — async callable that returns the actual data on demand.
                  set internally. stages never set this directly.

    Usage:
        raw = await flow.load()   # triggers _loader, returns T
    """
    descriptor: dict[str, Any]           # type, size, checksum — safe to log
    _loader:    Callable[[], Awaitable[T]] | None = field(default=None, repr=False)
    _cached:    T | None                  = field(default=None, repr=False)

    async def load(self) -> T:
        """
        Load the actual payload. Result is cached — calling load() twice
        does not trigger the loader twice.
        """
        if self._cached is not None:
            return self._cached
        if self._loader is None:
            raise RuntimeError("PayloadHandle has no loader — was this handle built correctly?")
        self._cached = await self._loader()
        return self._cached

    def offload(self) -> None:
        """
        Release the cached payload from memory.
        Called automatically by Flow.next() after a stage completes.
        Allows GC to free large data (raw PDF bytes, audio buffers, etc.)
        immediately after the stage that needed them is done.
        """
        self._cached = None


# ---------------------------------------------------------------------------
# Journal entry
# Every state transition is recorded here automatically.
# Developers never write journal entries — Flow writes them.
# ---------------------------------------------------------------------------

@dataclass
class JournalEntry:
    """
    A single recorded state transition in the Flow's history.

    Written automatically by .next(), .block(), .fail(), .warn().
    Never written by stage code directly.

    origin      — which stage produced this transition
    status      — what the status became after this transition
    duration_ms — how long the stage took (None if not measured)
    reason      — block/warn reason if applicable
    error       — error message if status=ERROR
    span_id     — the span that produced this entry
    timestamp   — monotonic clock at transition time
    payload_descriptor — the descriptor from PayloadHandle, safe to log
    """
    origin:               Origin | None
    status:               Status
    span_id:              str
    timestamp:            float = field(default_factory=time.monotonic)
    duration_ms:          float | None = None
    reason:               str | None = None
    error:                str | None = None
    payload_descriptor:   dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin":     self.origin.value if self.origin else None,
            "status":     self.status.value,
            "span_id":    self.span_id,
            "duration_ms": self.duration_ms,
            "reason":     self.reason,
            "error":      self.error,
            "payload":    self.payload_descriptor,
        }


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@dataclass
class Flow(Generic[T]):
    """
    The single transport type for all stage handoffs in Vraksha.

    Do not instantiate directly — use Flow.new().
    Do not mutate fields directly — use .next(), .block(), .fail(), .warn().
    Transition methods return a new Flow. Flow.next() also offloads the old
    payload cache so large raw data can be released promptly.

    Fields:
        handle      — lightweight payload descriptor + lazy loader
        status      — current status of this flow
        meta        — trace/span/timing metadata
        ctx         — the full VrakshaContext for this request
        journal     — append-only log of every state transition
        reason      — block/warn reason if applicable
        error       — error message if status=ERROR
        threat      — threat level if this flow was blocked or warned
    """

    handle:   PayloadHandle[T]
    status:   Status
    meta:     Meta
    ctx:      VrakshaContext
    journal:  list[JournalEntry]        = field(default_factory=list)
    reason:   str | None               = None
    error:    str | None               = None
    threat:   ThreatLevel              = ThreatLevel.NONE

    # ------------------------------------------------------------------
    # Construction — always use Flow.new()
    # ------------------------------------------------------------------

    @classmethod
    def new(
        cls,
        payload: T,
        session_id: str,
        user_id: str = "local-user",
        origin: Origin = Origin.INTAKE,
        trace_id: str | None = None,
    ) -> "Flow[T]":
        """
        Create a new Flow at the start of a request.
        Call this once in pipeline.py, never inside stages.

        payload     — the raw input, held inline only at birth.
                      immediately wrapped in a PayloadHandle.
        session_id  — which session this request belongs to.
        origin      — which layer is creating this (default: INTAKE).
        trace_id    — optional, if you have an external trace to continue.

        Example:
            flow = Flow.new(raw_input, session_id=session.id)
        """
        _payload = payload  # captured for closure

        async def _loader() -> T:
            return _payload

        handle = PayloadHandle(
            descriptor=_describe(payload),
            _loader=_loader,
        )
        meta = Meta(
            trace_id=trace_id or uuid4().hex,
            span_id=uuid4().hex[:8],
            origin=origin,
        )
        ctx = VrakshaContext.new(session_id=session_id, user_id=user_id, trace_id=meta.trace_id)
        ctx.advance(PipelineStage.INTAKE)

        initial_entry = JournalEntry(
            origin=origin,
            status=Status.OK,
            span_id=meta.span_id,
            payload_descriptor=handle.descriptor,
        )

        return cls(
            handle=handle,
            status=Status.OK,
            meta=meta,
            ctx=ctx,
            journal=[initial_entry],
        )

    # ------------------------------------------------------------------
    # Payload access — always async, always explicit
    # ------------------------------------------------------------------

    async def load(self) -> T:
        """
        Load the actual payload for this stage.
        Result is cached — calling load() twice is safe and free.

        Usage:
            raw = await flow.load()
            result = process(raw)
        """
        return await self.handle.load()

    # ------------------------------------------------------------------
    # Transitions — always return a new Flow, always write a journal entry
    # ------------------------------------------------------------------

    def next(
        self,
        payload: U,
        origin: Origin,
        started_at: float | None = None,
    ) -> "Flow[U]":
        """
        Advance to the next stage with a new payload.
        Old payload handle is offloaded — GC can free the raw data.
        A journal entry is written automatically.

        payload     — the output of the current stage
        origin      — which stage produced this
        started_at  — monotonic time.monotonic() at stage start, for duration

        Usage:
            return flow.next(result, Origin.SANITIZER, started)
        """
        self.handle.offload()

        async def _loader() -> U:
            return payload

        new_handle = PayloadHandle(
            descriptor=_describe(payload),
            _loader=_loader,
        )
        duration = _duration(started_at)
        new_meta  = self.meta.next_span(origin)
        if duration:
            new_meta.duration_ms = duration

        entry = JournalEntry(
            origin=origin,
            status=Status.OK,
            span_id=new_meta.span_id,
            duration_ms=duration,
            payload_descriptor=new_handle.descriptor,
        )

        return Flow(
            handle=new_handle,
            status=Status.OK,
            meta=new_meta,
            ctx=self.ctx, # This is the sauce right here, it preserves the context while updating current stage
            journal=[*self.journal, entry],
        )

    def block(
        self,
        reason: BlockReason,
        threat: ThreatLevel,
        origin: Origin,
        started_at: float | None = None,
    ) -> "Flow[T]":
        """
        Block this flow. Pipeline will not advance past this point.
        Context is marked blocked automatically.
        Journal entry is written automatically.

        reason  — why it was blocked (internal, never shown to user verbatim)
        threat  — how serious the threat was
        origin  — which stage is blocking

        Usage:
            return flow.block(BlockReason.MALICIOUS_CONTENT, ThreatLevel.HIGH, Origin.SANITIZER)
        """
        duration = _duration(started_at)
        new_meta = self.meta.next_span(origin)
        if duration:
            new_meta.duration_ms = duration

        self.ctx.mark_blocked(reason.value)

        entry = JournalEntry(
            origin=origin,
            status=Status.BLOCKED,
            span_id=new_meta.span_id,
            duration_ms=duration,
            reason=reason.value,
            payload_descriptor=self.handle.descriptor,
        )

        return Flow(
            handle=self.handle,
            status=Status.BLOCKED,
            meta=new_meta,
            ctx=self.ctx,
            journal=[*self.journal, entry],
            reason=reason.value,
            threat=threat,
        )

    def fail(
        self,
        error: VrakshaError | Exception,
        origin: Origin,
        started_at: float | None = None,
    ) -> "Flow[T]":
        """
        Mark this flow as failed due to an infrastructure or code error.
        Distinct from block() — this is a fault, not a threat.
        Context is marked failed automatically.
        Journal entry is written automatically.

        error   — the exception that caused the failure
        origin  — which stage failed

        Usage:
            except ModelUnavailableError as e:
                return flow.fail(e, Origin.VERIFIER)
        """
        error_str = _truncate(str(error), constants.MAX_ERROR_LENGTH)
        duration = _duration(started_at)
        new_meta = self.meta.next_span(origin)
        if duration:
            new_meta.duration_ms = duration

        self.ctx.mark_failed(error_str)

        entry = JournalEntry(
            origin=origin,
            status=Status.ERROR,
            span_id=new_meta.span_id,
            duration_ms=duration,
            error=error_str,
            payload_descriptor=self.handle.descriptor,
        )

        return Flow(
            handle=self.handle,
            status=Status.ERROR,
            meta=new_meta,
            ctx=self.ctx,
            journal=[*self.journal, entry],
            error=error_str,
        )

    def warn(
        self,
        reason: str,
        threat: ThreatLevel,
        origin: Origin,
        started_at: float | None = None,
    ) -> "Flow[T]":
        """
        Flag this flow with a warning. Pipeline continues.
        The next stage receives this Flow with status WARN, reason, and threat.
        Write to flow.ctx as well if later stages need durable warning state.
        Journal entry is written automatically.

        reason  — what was flagged
        threat  — LOW or MEDIUM (HIGH and CRITICAL should use block())
        origin  — which stage is warning

        Usage:
            return flow.warn("low confidence score", ThreatLevel.LOW, Origin.VERIFIER)
        """
        reason = _truncate(reason, constants.MAX_REASON_LENGTH)
        duration = _duration(started_at)
        new_meta = self.meta.next_span(origin)
        if duration:
            new_meta.duration_ms = duration

        entry = JournalEntry(
            origin=origin,
            status=Status.WARN,
            span_id=new_meta.span_id,
            duration_ms=duration,
            reason=reason,
            payload_descriptor=self.handle.descriptor,
        )

        return Flow(
            handle=self.handle,
            status=Status.WARN,
            meta=new_meta,
            ctx=self.ctx,
            journal=[*self.journal, entry],
            reason=reason,
            threat=threat,
        )

    # ------------------------------------------------------------------
    # Railway chaining — .then() skips stages automatically on failure
    # ------------------------------------------------------------------

    async def then(
        self,
        stage: Callable[["Flow[T]"], Awaitable["Flow[Any]"]],
    ) -> "Flow[Any]":
        """
        Chain stages Railway-style. If this flow should_stop,
        the stage is skipped entirely and this flow is returned unchanged.
        The pipeline never needs to check should_stop manually.

        Usage (pipeline.py):
            result = await (
                Flow.new(raw_input, session_id)
                .then(intake.process)
                .then(sanitizer.run)
                .then(normalizer.run)
                .then(verifier.verify)
                .then(orchestrator.run)
                .then(output_filter.run)
                .then(output.send)
            )

        Note: .then() is awaitable but the chain itself is not —
        each .then() must be awaited individually, or use the helper:
            result = await Flow.chain(flow, [stage1, stage2, stage3])
        """
        if self.should_stop:
            return self
        return await stage(self)

    @staticmethod
    async def chain(
        flow: "Flow[Any]",
        stages: list[Callable[["Flow[Any]"], Awaitable["Flow[Any]"]]],
    ) -> "Flow[Any]":
        """
        Run a list of stages in sequence, Railway-style.
        Any stage that blocks or fails short-circuits the rest.

        Usage:
            result = await Flow.chain(
                Flow.new(raw_input, session_id),
                [
                    intake.process,
                    sanitizer.run,
                    normalizer.run,
                    verifier.verify,
                    orchestrator.run,
                    output_filter.run,
                    output.send,
                ]
            )
        """
        current = flow
        for stage in stages:
            current = await current.then(stage)
        return current

    # ------------------------------------------------------------------
    # Status checks
    # ------------------------------------------------------------------

    @property
    def ok(self) -> bool:
        return self.status == Status.OK

    @property
    def blocked(self) -> bool:
        return self.status == Status.BLOCKED

    @property
    def warned(self) -> bool:
        return self.status == Status.WARN

    @property
    def errored(self) -> bool:
        return self.status == Status.ERROR

    @property
    def should_stop(self) -> bool:
        """True if the pipeline must not advance. Checked automatically by .then()."""
        return self.status in (Status.BLOCKED, Status.ERROR)

    # ------------------------------------------------------------------
    # Observability — summary() is all you ever log
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """
        Minimal dict for structured logging.
        Safe to log — never includes raw payload, PII, or sensitive content.

        Usage:
            logger.warning("flow blocked", **flow.summary())
        """
        return {
            "trace_id":    self.meta.trace_id,
            "span_id":     self.meta.span_id,
            "origin":      self.meta.origin.value if self.meta.origin else None,
            "status":      self.status.value,
            "duration_ms": self.meta.duration_ms,
            "reason":      self.reason,
            "error":       self.error,
            "threat":      self.threat.value,
            "stage":       self.ctx.current_stage.value,
            "total_ms":    round(self.ctx.total_duration_ms, 2),
        }

    def audit(self) -> list[dict[str, Any]]:
        """
        Full journal as a list of dicts. Use for dead letter output,
        post-mortem debugging, and security audits.
        Each entry is safe to log — descriptors only, no raw payload.

        Usage:
            dead_letter_writer.write(flow.audit())
        """
        return [entry.as_dict() for entry in self.journal]

    def replay(self) -> str:
        """
        Human-readable journey of this flow through the pipeline.
        For debugging in development — prints every stage transition.

        Usage:
            print(flow.replay())
        """
        lines = [f"Flow {self.meta.trace_id[:8]}... journey:"]
        for i, entry in enumerate(self.journal):
            duration = f"{entry.duration_ms:.1f}ms" if entry.duration_ms else "—"
            status   = entry.status.value.upper()
            origin   = entry.origin.value if entry.origin else "—"
            note     = entry.reason or entry.error or ""
            lines.append(f"  {i:02d}. [{status:8s}] {origin:20s} {duration:>10s}  {note}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"Flow("
            f"status={self.status.value}, "
            f"origin={self.meta.origin}, "
            f"trace={self.meta.trace_id[:8]}..., "
            f"span={self.meta.span_id}, "
            f"hops={len(self.journal)}"
            f")"
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _describe(payload: Any) -> dict[str, Any]:
    """
    Build a safe descriptor for a payload. Never includes raw data.
    Used in PayloadHandle.descriptor and JournalEntry.payload_descriptor.
    """
    descriptor: dict[str, Any] = {"type": type(payload).__name__}
    if isinstance(payload, (bytes, bytearray)):
        descriptor["size_bytes"] = len(payload)
    elif isinstance(payload, str):
        descriptor["size_chars"] = len(payload)
    elif hasattr(payload, "__len__"):
        try:
            descriptor["length"] = len(payload)  # type: ignore[arg-type]
        except Exception:
            pass
    return descriptor


def _duration(started_at: float | None) -> float | None:
    """Calculate duration in ms from a monotonic start time. None if not measured."""
    if started_at is None:
        return None
    return round((time.monotonic() - started_at) * 1000, 2)


def _truncate(text: str, limit: int) -> str:
    """
    Cap an observability string to `limit` chars.

    reason/error fields can embed free-form text (verifier reasons, wrapped
    exception messages that may contain user content). Truncating here keeps
    summary()/journal output bounded so "safe to log" holds in practice.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
