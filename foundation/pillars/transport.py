"""
foundation/pillars/transport.py

The low-level internal message envelope for Vraksha.

Note: Origin was moved to foundation/pillars/types.py.
      Import it from there or via foundation directly:
          from foundation import Origin

Note on usage:
  Most stage code should use Flow (foundation/flow.py), not Envelope directly.
  Envelope is the low-level primitive that Flow is built on.
  Use Envelope directly only when you need fine-grained control
  outside the standard pipeline (e.g. internal worker communication).

Rules:
  1. Never unwrap without checking status first.
  2. Never mutate — always return a new Envelope.
  3. trace_id never changes. span_id always does.
  4. This file has zero imports from the rest of Vraksha.
     Everything imports from here, never the reverse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import uuid4

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class Status(str, Enum):
    """
    What happened at this stage.

    OK       — passed cleanly, payload is valid, continue.
    BLOCKED  — hard stop. payload explains what was blocked and why.
               pipeline must not continue. user gets a system message.
    WARN     — passed but flagged. orchestrator sees the warning.
               pipeline continues with caution.
    ERROR    — something broke (timeout, exception, infra failure).
               distinct from BLOCKED — this is not a threat, it is a fault.
    PENDING  — async work in progress, not yet resolved.
               used internally by parallel workers before joining.
    """
    OK      = "ok"
    BLOCKED = "blocked"
    WARN    = "warn"
    ERROR   = "error"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Metadata — always present, carried through the full request lifetime
# ---------------------------------------------------------------------------

@dataclass
class Meta:
    """
    Tracing metadata attached to every envelope.

    trace_id    — born at intake, never changes for the lifetime of a request.
                  use this to correlate all log lines for one user turn.
    span_id     — generated fresh at each stage hop.
                  use this to identify exactly which stage produced this envelope.
    origin      — which stage produced this envelope.
                  type is Any to avoid circular import with types.py.
                  in practice always an Origin enum value.
    timestamp   — monotonic clock at creation. use for relative timing only.
    duration_ms — filled in by the stage when it finishes work.
                  left as None if the stage didn't measure itself.
    """
    trace_id:     str        = field(default_factory=lambda: uuid4().hex)
    span_id:      str        = field(default_factory=lambda: uuid4().hex[:8])
    origin:       Any | None = None
    timestamp:    float      = field(default_factory=time.monotonic)
    duration_ms:  float | None = None

    def next_span(self, origin: Any) -> "Meta":
        """
        Produce a new Meta for the next stage.
        trace_id is preserved. span_id is fresh. origin is updated.
        """
        return Meta(
            trace_id=self.trace_id,
            span_id=uuid4().hex[:8],
            origin=origin,
        )


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

@dataclass
class Envelope(Generic[T]):
    """
    The low-level internal transport primitive for Vraksha.

    Most stage code uses Flow (foundation/flow.py) which is built on top
    of this. Use Envelope directly only when you need low-level control.

    Every function that crosses a stage boundary:
      - takes  an Envelope[SomeInputType]
      - returns an Envelope[SomeOutputType]

    Never pass raw dicts, raw strings, or bare Pydantic models between stages.
    Always wrap in an Envelope.

    payload  — the actual data for this stage. always present, even on error,
               so downstream stages can inspect what caused the failure.
    status   — what happened. check this before touching payload.
    meta     — tracing metadata. always present.
    reason   — human-readable explanation for BLOCKED or WARN status.
               shown in dead letter logs. never shown to users directly.
    error    — exception message for ERROR status.
               infrastructure faults, timeouts, unexpected exceptions.
    """
    payload:  T
    status:   Status
    meta:     Meta
    reason:   str | None = None
    error:    str | None = None

    # ------------------------------------------------------------------
    # Status checks — always use these, never compare status directly
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
    def pending(self) -> bool:
        return self.status == Status.PENDING

    @property
    def should_stop(self) -> bool:
        """True if the pipeline must not continue past this point."""
        return self.status in (Status.BLOCKED, Status.ERROR)

    # ------------------------------------------------------------------
    # Factory helpers — use these to construct envelopes, never __init__
    # ------------------------------------------------------------------

    @classmethod
    def ok_(
        cls,
        payload: T,
        origin: Any,
        meta: Meta | None = None,
    ) -> "Envelope[T]":
        m = (meta.next_span(origin) if meta else Meta(origin=origin))
        return cls(payload=payload, status=Status.OK, meta=m)

    @classmethod
    def block_(
        cls,
        reason: str,
        payload: T,
        origin: Any,
        meta: Meta | None = None,
    ) -> "Envelope[T]":
        m = (meta.next_span(origin) if meta else Meta(origin=origin))
        return cls(payload=payload, status=Status.BLOCKED, meta=m, reason=reason)

    @classmethod
    def warn_(
        cls,
        reason: str,
        payload: T,
        origin: Any,
        meta: Meta | None = None,
    ) -> "Envelope[T]":
        m = (meta.next_span(origin) if meta else Meta(origin=origin))
        return cls(payload=payload, status=Status.WARN, meta=m, reason=reason)

    @classmethod
    def error_(
        cls,
        error: str,
        payload: T,
        origin: Any,
        meta: Meta | None = None,
    ) -> "Envelope[T]":
        m = (meta.next_span(origin) if meta else Meta(origin=origin))
        return cls(payload=payload, status=Status.ERROR, meta=m, error=error)

    @classmethod
    def pending_(
        cls,
        payload: T,
        origin: Any,
        meta: Meta | None = None,
    ) -> "Envelope[T]":
        m = (meta.next_span(origin) if meta else Meta(origin=origin))
        return cls(payload=payload, status=Status.PENDING, meta=m)

    # ------------------------------------------------------------------
    # Propagation helpers
    # ------------------------------------------------------------------

    def propagate(self, new_payload: Any, origin: Any) -> "Envelope[Any]":
        """
        Carry the same trace_id forward into the next stage with a new payload.
        Use this when a stage transforms the payload and passes it on.

        Example:
            norm_env = san_env.propagate(normalized_data, Origin.NORMALIZER)
        """
        return Envelope(
            payload=new_payload,
            status=self.status,
            meta=self.meta.next_span(origin),
            reason=self.reason,
            error=self.error,
        )

    def forward_block(self, origin: Any) -> "Envelope[T]":
        """
        Pass a BLOCKED envelope through a stage unchanged.
        Use when a stage receives a blocked envelope and must return immediately.

        Example:
            if not env.ok:
                return env.forward_block(Origin.NORMALIZER)
        """
        return Envelope(
            payload=self.payload,
            status=Status.BLOCKED,
            meta=self.meta.next_span(origin),
            reason=self.reason,
            error=self.error,
        )

    def with_duration(self, started_at: float) -> "Envelope[T]":
        """
        Attach duration_ms to this envelope's meta.
        Call at the end of a stage:

            started = time.monotonic()
            result = do_work()
            return result.with_duration(started)
        """
        elapsed = (time.monotonic() - started_at) * 1000
        new_meta = Meta(
            trace_id=self.meta.trace_id,
            span_id=self.meta.span_id,
            origin=self.meta.origin,
            timestamp=self.meta.timestamp,
            duration_ms=round(elapsed, 2),
        )
        return Envelope(
            payload=self.payload,
            status=self.status,
            meta=new_meta,
            reason=self.reason,
            error=self.error,
        )

    # ------------------------------------------------------------------
    # Debug / logging
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """
        Minimal dict for structured logging.
        Never log the full payload — it may contain sensitive data.
        Log the summary, then log payload fields selectively.
        """
        return {
            "trace_id":    self.meta.trace_id,
            "span_id":     self.meta.span_id,
            "origin":      self.meta.origin,
            "status":      self.status,
            "duration_ms": self.meta.duration_ms,
            "reason":      self.reason,
            "error":       self.error,
        }

    def __repr__(self) -> str:
        return (
            f"Envelope("
            f"status={self.status.value}, "
            f"origin={self.meta.origin}, "
            f"trace={self.meta.trace_id[:8]}..., "
            f"span={self.meta.span_id}"
            f")"
        )
