"""Policy checks for expert-to-expert communication.

This is intentionally fail-closed. An expert route must be explicitly allowed,
and even allowed routes can be blocked by topic or missing justification.
"""

from __future__ import annotations

from .decision import OrchestratorDecision
from .messages import ExpertMessageRequest


class ExpertMessagePolicy:
    """Decide whether one expert may send a message to another expert."""

    def __init__(
        self,
        allowed_routes: set[tuple[str, str]] | None = None,
        blocked_topics: set[str] | None = None,
    ) -> None:
        """Create a policy from explicit route and topic allow/block sets."""
        self.allowed_routes = allowed_routes or set()
        self.blocked_topics = blocked_topics or set()

    def decide(self, request: ExpertMessageRequest) -> OrchestratorDecision:
        """Return the allow/block decision for a proposed expert message."""
        if request.source.kind != "expert" or request.target.kind != "expert":
            return OrchestratorDecision(
                request_id=request.request_id,
                decision="block",
                reason="expert message routes must be expert-to-expert",
            )

        if request.topic in self.blocked_topics:
            return OrchestratorDecision(
                request_id=request.request_id,
                decision="block",
                reason=f"topic is blocked: {request.topic}",
            )

        route = (request.source.name, request.target.name)
        if route not in self.allowed_routes:
            return OrchestratorDecision(
                request_id=request.request_id,
                decision="block",
                reason="route is not explicitly allowed",
            )

        if not request.reason.strip():
            return OrchestratorDecision(
                request_id=request.request_id,
                decision="block",
                reason="reason is required",
            )

        return OrchestratorDecision(
            request_id=request.request_id,
            decision="allow",
            reason="route allowed by orchestrator policy",
        )
