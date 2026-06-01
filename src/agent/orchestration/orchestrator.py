"""Agent-owned orchestration coordinator.

This is the central boundary for expert collaboration. It applies policy,
records what it observed, and exposes guardrail review so the main agent can
block unsafe flows before they become tool or expert work.
"""

from __future__ import annotations

from .guardrails import (
    AgentGuardrailContext,
    AgentGuardrailDecision,
    AgentGuardrailPolicy,
)
from .decision import OrchestratorDecision
from .log import ObservedExpertMessage
from .messages import ExpertMessageRequest
from .policy import ExpertMessagePolicy


class AgentOrchestrator:
    """Agent-owned boundary for expert communication and flow control."""

    def __init__(
        self,
        policy: ExpertMessagePolicy | None = None,
        guardrails: AgentGuardrailPolicy | None = None,
    ) -> None:
        """Create an orchestrator with explicit or default policies."""
        self.policy = policy or ExpertMessagePolicy()
        self.guardrails = guardrails or AgentGuardrailPolicy()
        self._observed: list[ObservedExpertMessage] = []

    @property
    def observed_messages(self) -> tuple[ObservedExpertMessage, ...]:
        """Return immutable view of expert messages reviewed this session."""
        return tuple(self._observed)

    def review_expert_message(
        self,
        request: ExpertMessageRequest,
    ) -> OrchestratorDecision:
        """Review, decide, and record an expert-to-expert message request."""
        decision = self.policy.decide(request)
        self._observed.append(
            ObservedExpertMessage(request=request, decision=decision)
        )
        return decision

    def review_guardrails(
        self,
        context: AgentGuardrailContext,
    ) -> AgentGuardrailDecision:
        """Run general agent guardrails for a proposed orchestration action."""
        return self.guardrails.decide(context)


Orchestrator = AgentOrchestrator
