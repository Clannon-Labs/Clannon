"""
Shared pipeline payload contracts.

These dataclasses describe the shape of payloads that travel through Flow. They
are not transport themselves; Flow remains the only runtime carrier between
stages. Keeping cross-stage schemas here avoids coupling one stage to another
stage's implementation module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .pillars.types import ThreatLevel


@dataclass(slots=True)
class NormalizedInput:
    """
    Structured payload passed from normalizer to verifier/orchestrator.

    content is text when code-only normalization can produce text. native_payload
    is preserved when the target model supports that modality directly.
    requires_expert marks media that needs a capable model/tool later because
    normalizer itself stays code-only.
    """
    modality: str
    content_type: str
    content: str | None = None
    native_payload: Any | None = None
    target_layer: str = "orchestrator"
    target_provider: str | None = None
    target_model: str | None = None
    preserved_native: bool = False
    requires_expert: bool = False
    required_capability: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
