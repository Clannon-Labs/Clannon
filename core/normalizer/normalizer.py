"""
Code-only input normalizer.

The normalizer receives the sanitized payload from the sanitizer layer and
turns it into a structured handoff for later LLM/tool stages. It does not call
an LLM. Instead, it uses the root model registry to decide whether the target
model can receive native media or whether a later expert/model needs to help.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from foundation import (
    Flow,
    Origin,
    Modality,
    PipelineStage,
    constants,
    load_model_registry,
)
from .extractors import extract_pdf_pages
from .utils import payload_to_text, truncate_text


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


def _normalize_text(payload: Any) -> NormalizedInput:
    """Return text with stable Unicode decoding and configured length metadata."""
    text, truncated = truncate_text(
        payload_to_text(payload),
        constants.MAX_TEXT_INPUT_CHARS,
    )

    return NormalizedInput(
        modality=Modality.TEXT.value,
        content_type="text/plain",
        content=text,
        metadata={
            "chars": len(text),
            "truncated": truncated,
        },
    )


def _normalize_pdf(payload: Any) -> NormalizedInput:
    """
    Extract PDF text with PyMuPDF.

    PDF extraction is code-only and preserves page boundaries so later LLM
    stages can cite or reason over page-local context.
    """
    pages = extract_pdf_pages(payload)
    content = "\n\n".join(
        f"[page {page['page']}]\n{page['text']}"
        for page in pages
        if page["text"]
    )
    content, truncated = truncate_text(content, constants.MAX_TEXT_INPUT_CHARS)

    return NormalizedInput(
        modality=Modality.PDF.value,
        content_type="text/markdown",
        content=content,
        metadata={
            "pages": len(pages),
            "text_pages": sum(1 for page in pages if page["text"]),
            "truncated": truncated,
        },
    )


def _preserve_native(
    payload: Any,
    modality: str,
    target_layer: str,
    target_provider: str | None,
    target_model: str | None,
) -> NormalizedInput:
    """Return native media unchanged when the target model can consume it."""
    return NormalizedInput(
        modality=modality,
        content_type=f"{modality}/native",
        native_payload=payload,
        target_layer=target_layer,
        target_provider=target_provider,
        target_model=target_model,
        preserved_native=True,
        metadata={
            "handoff": "native_media",
        },
    )


def _requires_expert(
    payload: Any,
    modality: str,
    target_layer: str,
    target_provider: str | None,
    target_model: str | None,
) -> NormalizedInput:
    """
    Mark media that code-only normalization cannot faithfully convert.

    The next layer can route this to the configured media_expert instead of
    forcing lossy OCR/caption/transcription here.
    """
    return NormalizedInput(
        modality=modality,
        content_type=f"{modality}/native",
        native_payload=payload,
        target_layer=target_layer,
        target_provider=target_provider,
        target_model=target_model,
        preserved_native=False,
        requires_expert=True,
        required_capability=modality,
        metadata={
            "handoff": "media_expert_required",
        },
    )


def _primary_modality(flow: Flow) -> str:
    """Return the first detected modality, falling back to text."""
    if flow.ctx.detected_modalities:
        return flow.ctx.detected_modalities[0]
    return Modality.TEXT.value


def normalize_payload(
    payload: Any,
    modality: str,
    target_layer: str = "orchestrator",
) -> NormalizedInput:
    """
    Normalize sanitized payload according to the target model capabilities.

    Text and PDF are normalized with code. Image/audio/video are preserved when
    the target model declares support; otherwise the result marks that a media
    expert is required later.
    """
    registry = load_model_registry()
    target_model = registry.for_layer(target_layer)

    if modality == Modality.TEXT.value:
        normalized = _normalize_text(payload)
    elif modality == Modality.PDF.value:
        normalized = _normalize_pdf(payload)
    elif target_model.supports(modality):
        normalized = _preserve_native(
            payload,
            modality,
            target_layer,
            target_model.provider,
            target_model.model,
        )
    else:
        normalized = _requires_expert(
            payload,
            modality,
            target_layer,
            target_model.provider,
            target_model.model,
        )

    normalized.target_layer = target_layer
    normalized.target_provider = target_model.provider
    normalized.target_model = target_model.model
    return normalized


async def run(flow: Flow) -> Flow:
    """
    Pipeline entry point for normalization.

    This stage receives the sanitizer output, creates a NormalizedInput object,
    stores it on flow.ctx.normalized_input, and passes it forward.
    """
    started = time.monotonic()

    try:
        payload = await flow.load()
        modality = _primary_modality(flow)
        normalized = normalize_payload(payload, modality=modality)

        flow.ctx.normalized_input = normalized
        flow.ctx.advance(PipelineStage.NORMALIZING)
        return flow.next(normalized, Origin.NORMALIZER, started)

    except Exception as exc:
        return flow.fail(exc, Origin.NORMALIZER, started)
