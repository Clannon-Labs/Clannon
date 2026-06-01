"""Decision records returned by the agent orchestrator.

The rest of the system should not infer approval from missing errors. Every
reviewed request receives an explicit allow/block decision with an explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any, Literal

Decision = Literal["allow", "block"]


@dataclass(slots=True, frozen=True)
class OrchestratorDecision:
    """Immutable allow/block result for an observed orchestration request."""

    request_id: str
    decision: Decision
    reason: str
    observed: bool = True
    created_ns: int = field(default_factory=monotonic_ns)

    @property
    def allowed(self) -> bool:
        """Convenience boolean for call sites that only need allow/block."""
        return self.decision == "allow"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for logs and test assertions."""
        return {
            "request_id": self.request_id,
            "decision": self.decision,
            "reason": self.reason,
            "observed": self.observed,
            "created_ns": self.created_ns,
        }
