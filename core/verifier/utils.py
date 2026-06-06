"""Shared verifier helpers."""

from __future__ import annotations

from typing import Any

from foundation import Flow, NormalizedInput, ThreatLevel, VerificationResult

from .constants import ROUTING_DIRECT, VERIFIER_EXCERPT_CHARS


def verification_result(
    *,
    proceed: bool,
    dangerous: bool = False,
    warn: bool = False,
    threat_level: ThreatLevel = ThreatLevel.NONE,
    reason: str | None = None,
    categories: list[str] | None = None,
    routing_action: str = ROUTING_DIRECT,
    normalized: NormalizedInput | None = None,
    metadata: dict[str, Any] | None = None,
) -> VerificationResult:
    """Build a result while copying routing fields from NormalizedInput."""
    return VerificationResult(
        proceed=proceed,
        dangerous=dangerous,
        warn=warn,
        threat_level=threat_level,
        reason=reason,
        categories=categories or [],
        routing_action=routing_action,
        requires_expert=bool(normalized.requires_expert) if normalized else False,
        required_capability=normalized.required_capability if normalized else None,
        target_provider=normalized.target_provider if normalized else None,
        target_model=normalized.target_model if normalized else None,
        metadata=metadata or {},
    )


def content_excerpt(content: str | None) -> tuple[str, bool]:
    """Return a bounded content view for verifier checks and metadata."""
    if not content:
        return "", False
    excerpt = content[:VERIFIER_EXCERPT_CHARS]
    return excerpt, len(content) > VERIFIER_EXCERPT_CHARS


def sanitizer_summary(flow: Flow[Any]) -> dict[str, Any]:
    """Create a compact, safe-to-store sanitizer summary for verifier context."""
    sanitization = flow.ctx.sanitization
    if not isinstance(sanitization, dict):
        return {}

    workers = []
    for worker_result in sanitization.get("workers", []):
        workers.append(
            {
                "name": type(worker_result).__name__,
                "threat_level": getattr(worker_result, "threat_level", None),
                "passed": getattr(worker_result, "passed", None),
                "reason": getattr(worker_result, "reason", None),
            }
        )

    return {
        "pre_sanitization": type(sanitization.get("pre_sanitization")).__name__,
        "workers": workers,
        "sanitized_outputs": sorted((sanitization.get("sanitized_outputs") or {}).keys()),
    }
