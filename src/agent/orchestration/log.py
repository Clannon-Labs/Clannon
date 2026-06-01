"""Observation records for orchestrator-reviewed expert messages.

The orchestrator keeps both the original request and the decision so later
auditing can answer: who asked to talk to whom, why, and what happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .decision import OrchestratorDecision
from .messages import ExpertMessageRequest


@dataclass(slots=True, frozen=True)
class ObservedExpertMessage:
    """Pair an expert message request with the decision made about it."""

    request: ExpertMessageRequest
    decision: OrchestratorDecision

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly nested audit record."""
        return {
            "request": self.request.to_dict(),
            "decision": self.decision.to_dict(),
        }
