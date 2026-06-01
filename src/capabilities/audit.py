from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any

from .contracts import CapabilityRequest, CapabilityResult


@dataclass(slots=True, frozen=True)
class AuditEvent:
    """One recorded broker decision.

    The broker currently keeps these events in memory, but the shape is meant
    to survive a later durable audit store. Each event captures who asked for a
    capability, whether the request was allowed, and the policy or execution
    error code when the request failed.
    """

    request_id: str
    capability: str
    caller: dict[str, str]
    allowed: bool
    reason: str
    error_code: str | None = None
    created_ns: int = field(default_factory=monotonic_ns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "capability": self.capability,
            "caller": self.caller,
            "allowed": self.allowed,
            "reason": self.reason,
            "error_code": self.error_code,
            "created_ns": self.created_ns,
        }


class InMemoryAuditLog:
    """Append-only audit sink used by the first broker implementation.

    This intentionally exposes only copy-style reads through ``events()`` so
    callers can inspect decisions in tests or diagnostics without mutating the
    broker's internal event list.
    """

    def __init__(self) -> None:
        """Create an empty audit log for one broker instance or test."""
        self._events: list[AuditEvent] = []

    def record(self, request: CapabilityRequest, result: CapabilityResult) -> None:
        """Store the final decision for a capability request/result pair."""
        self._events.append(
            AuditEvent(
                request_id=request.request_id,
                capability=request.capability,
                caller=request.caller.to_dict(),
                allowed=result.success,
                reason=request.reason,
                error_code=None if result.error is None else result.error.code,
            )
        )

    def events(self) -> list[AuditEvent]:
        """Return a snapshot of recorded events in insertion order."""
        return list(self._events)
