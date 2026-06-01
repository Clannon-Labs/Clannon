"""Message contracts for expert-to-expert communication.

Experts are not allowed to call each other directly. They build one of these
requests and hand it to the agent-owned orchestrator, which can observe, allow,
or block the attempted communication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any
from uuid import uuid4

from src.capabilities.contracts import Actor


@dataclass(slots=True, frozen=True)
class ExpertMessageRequest:
    """A proposed message from one expert to another.

    The request is immutable once created so the orchestrator can safely log the
    exact payload and reason it reviewed.
    """

    source: Actor
    target: Actor
    topic: str
    payload: dict[str, Any]
    reason: str
    request_id: str = field(default_factory=lambda: uuid4().hex)
    parent_id: str | None = None
    created_ns: int = field(default_factory=monotonic_ns)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for logging or audit output."""
        return {
            "request_id": self.request_id,
            "parent_id": self.parent_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "topic": self.topic,
            "payload": self.payload,
            "reason": self.reason,
            "created_ns": self.created_ns,
        }
