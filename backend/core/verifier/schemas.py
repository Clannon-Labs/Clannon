"""Schemas owned by the verifier: the verifier-LLM I/O models plus the
VerificationResult contract written to ctx.verifier_result.

VerificationResult used to live in foundation, but the verifier is its only
consumer, so it belongs here (foundation never references it)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from foundation import ThreatLevel


class VerifierInputView(BaseModel):
    """Compact, safe view sent to the verifier model."""
    modality: str
    content_type: str
    content_excerpt: str
    deterministic_categories: list[str] = Field(default_factory=list)
    deterministic_score: int = 0
    matched_rules: list[str] = Field(default_factory=list)
    excerpt_truncated: bool = False
    sanitizer_summary: dict = Field(default_factory=dict)
    target_provider: str | None = None
    target_model: str | None = None


class VerifierLLMResult(BaseModel):
    """Strict verifier-model output."""
    proceed: bool
    dangerous: bool = False
    warn: bool = False
    threat_level: Literal["none", "low", "medium", "high", "critical"]
    reason: str | None = None
    categories: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """
    Structured verifier output stored on flow.ctx.verifier_result.

    The verifier never produces user-facing prose. reason is internal context
    for logs, dead letters, and later safe orchestration decisions.
    """
    proceed: bool
    dangerous: bool = False
    warn: bool = False
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    categories: list[str] = field(default_factory=list)
    routing_action: str = "direct"
    requires_expert: bool = False
    required_capability: str | None = None
    target_provider: str | None = None
    target_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
