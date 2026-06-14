"""
Cross-stage pipeline payloads.

These dataclasses describe the shape of payloads that travel through Flow between
stages. They are not transport themselves; Flow remains the only runtime carrier.
Keeping cross-stage schemas here avoids coupling one stage to another stage's
implementation module.

(Single-stage payloads live with their stage — e.g. the verifier's
VerificationResult lives in core/verifier/schemas.py. The memory boundary
contracts live next door in contracts/memory.py.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(slots=True)
class OrchestratorResponse:
    """
    The orchestrator's draft answer, stored on ctx.orchestrator_response. This is
    the input to the output filter, not the final user-facing text.
    """
    text: str
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    finding_refs: list[str] = field(default_factory=list)   # -> ctx.expert_findings
