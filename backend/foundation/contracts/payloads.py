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
from typing import Any, Literal


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

    @classmethod
    def coerce(cls, payload: Any) -> "NormalizedInput":
        """
        Return `payload` unchanged if it is already a NormalizedInput, else
        synthesize a trivial one from a raw payload.

        This is what lets the normalizer be an OPTIONAL stage: the verifier and the
        orchestrator call `coerce(await flow.load())`, so if the normalizer is
        removed from the pipeline they receive an un-normalized-but-valid
        NormalizedInput (text content for a str, a preserved native payload for
        bytes) instead of crashing on a raw payload. When the normalizer is present
        this is a no-op — its output is already a NormalizedInput.
        """
        if isinstance(payload, NormalizedInput):
            return payload
        if isinstance(payload, str):
            return cls(modality="text", content_type="text/plain", content=payload)
        if isinstance(payload, (bytes, bytearray)):
            return cls(
                modality="binary",
                content_type="application/octet-stream",
                native_payload=bytes(payload),
                preserved_native=True,
            )
        return cls(modality="text", content_type="text/plain", content=str(payload))


@dataclass(slots=True)
class OrchestratorResponse:
    """
    The orchestrator's draft answer, stored on ctx.orchestrator_response. This is
    the input to the output filter, not the final user-facing text.
    """
    text: str
    # Post-filter presentation intent. `text` is filtered in BOTH modes; API
    # delivery decides whether accepted text becomes open conversational chat
    # or an inline report sheet. Default preserves legacy/test producers that
    # predate explicit orchestrator intent; the live orchestrator always sets it.
    presentation: Literal["chat", "report"] = "report"
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    finding_refs: list[str] = field(default_factory=list)   # -> ctx.expert_findings
    message: str = ""   # the orchestrator's CONVERSATIONAL reply to the user (the chat
                        # bubble), separate from `text` (the deliverable/report). May be set
                        # with no `text` (pure conversation) or alongside it (note + deliverable).
