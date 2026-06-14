"""
foundation/transport/primitives.py

Low-level transport primitives for Vraksha: Status and Meta. Flow
(foundation/transport/flow.py) — the transport every stage uses — is built on
them.

Rules:
  1. trace_id never changes. span_id always does.
  2. This file has zero runtime imports from the rest of Vraksha (the Origin
     import below is type-checking only). Everything imports from here, never
     the reverse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ..vocab.types import Origin

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
    """
    OK      = "ok"
    BLOCKED = "blocked"
    WARN    = "warn"
    ERROR   = "error"


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
    origin      — which stage produced this envelope (an Origin enum value).
    timestamp   — monotonic clock at creation. use for relative timing only.
    duration_ms — filled in by the stage when it finishes work.
                  left as None if the stage didn't measure itself.
    """
    trace_id:     str             = field(default_factory=lambda: uuid4().hex)
    span_id:      str             = field(default_factory=lambda: uuid4().hex[:8])
    origin:       "Origin | None" = None
    timestamp:    float           = field(default_factory=time.monotonic)
    duration_ms:  float | None    = None

    def next_span(self, origin: "Origin") -> "Meta":
        """
        Produce a new Meta for the next stage.
        trace_id is preserved. span_id is fresh. origin is updated.
        """
        return Meta(
            trace_id=self.trace_id,
            span_id=uuid4().hex[:8],
            origin=origin,
        )
