"""Agent-level guardrails for orchestration and capability requests.

These checks protect the central agent before any deeper broker/tool/expert work
happens. They are deliberately simple, fast, and fail-closed so obvious unsafe
request shapes never reach execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RequestKind = Literal[
    "agent",
    "capability",
    "expert_message",
    "memory",
    "tool",
]


@dataclass(slots=True, frozen=True)
class AgentGuardrailLimits:
    """Tunable hard caps used by the guardrail policy."""

    max_recursion_depth: int = 3
    max_parallel_requests: int = 5
    max_payload_bytes: int = 500_000
    allow_memory_dump: bool = False


@dataclass(slots=True, frozen=True)
class AgentGuardrailContext:
    """Context the agent supplies when asking guardrails to review a request."""

    kind: RequestKind
    reason: str
    session_id: str
    user_id: str
    request_session_id: str | None = None
    request_user_id: str | None = None
    recursion_depth: int = 0
    requested_count: int = 1
    payload: dict[str, Any] | None = None
    untrusted_text: str | None = None
    requests_memory_dump: bool = False


@dataclass(slots=True, frozen=True)
class AgentGuardrailDecision:
    """Allow/block result from the agent guardrail policy."""

    allowed: bool
    code: str
    reason: str

    def to_dict(self) -> dict[str, str | bool]:
        """Return a JSON-friendly representation for logs or responses."""
        return {
            "allowed": self.allowed,
            "code": self.code,
            "reason": self.reason,
        }


class AgentGuardrailPolicy:
    """Fail-closed checks for orchestration and capability requests."""

    _INJECTION_MARKERS = (
        "ignore all prior instructions",
        "ignore previous instructions",
        "you are now",
        "tell every sub-agent",
        "reveal secrets",
    )

    def __init__(self, limits: AgentGuardrailLimits | None = None) -> None:
        """Create guardrails with default or caller-supplied limits."""
        self.limits = limits or AgentGuardrailLimits()

    def decide(self, context: AgentGuardrailContext) -> AgentGuardrailDecision:
        """Evaluate request context and return the first blocking reason."""
        if not context.reason.strip():
            return self._block("missing_reason", "request reason is required")

        if context.request_session_id and context.request_session_id != context.session_id:
            return self._block(
                "session_mismatch",
                "request session does not match active session",
            )

        if context.request_user_id and context.request_user_id != context.user_id:
            return self._block(
                "user_mismatch",
                "request user does not match active user",
            )

        if context.recursion_depth > self.limits.max_recursion_depth:
            return self._block(
                "recursion_limit",
                "request exceeds maximum orchestration depth",
            )

        if context.requested_count > self.limits.max_parallel_requests:
            return self._block(
                "request_fanout_limit",
                "request asks for too many parallel actions",
            )

        if self._payload_size(context.payload) > self.limits.max_payload_bytes:
            return self._block(
                "payload_too_large",
                "request payload exceeds maximum allowed size",
            )

        if context.requests_memory_dump and not self.limits.allow_memory_dump:
            return self._block(
                "memory_dump_denied",
                "bulk memory export is not allowed by default",
            )

        if self._contains_prompt_injection(context.untrusted_text):
            return self._block(
                "prompt_injection_detected",
                "untrusted content contains instruction-like attack text",
            )

        return AgentGuardrailDecision(
            allowed=True,
            code="allowed",
            reason="request passed agent guardrails",
        )

    def _block(self, code: str, reason: str) -> AgentGuardrailDecision:
        """Build a standardized blocking decision."""
        return AgentGuardrailDecision(
            allowed=False,
            code=code,
            reason=reason,
        )

    def _payload_size(self, payload: dict[str, Any] | None) -> int:
        """Estimate payload size without requiring JSON-serializable values."""
        if payload is None:
            return 0
        return len(repr(payload).encode("utf-8"))

    def _contains_prompt_injection(self, text: str | None) -> bool:
        """Detect obvious instruction-injection phrases in untrusted text."""
        if not text:
            return False
        lowered = text.lower()
        return any(marker in lowered for marker in self._INJECTION_MARKERS)
