"""
Normalization logic: turn a sanitized payload + its modality into a
NormalizedInput handoff.

This is the normalizer's near-root logic, kept out of the stage door
(normalizer.py) so the door reads as pure assemble-and-execute. Everything here
is Flow-agnostic — it takes a raw payload and a modality string, never a Flow —
and stays code-only (no LLM calls). The target model's declared capabilities
decide whether media is preserved natively or deferred to a later expert.
"""

from __future__ import annotations

from typing import Any

from foundation import (
    Modality,
    NormalizedInput,
)
import settings
from registry.config import load_model_registry

from .extractors import extract_pdf_pages
from .utils import payload_to_text, truncate_text


def _normalize_text(payload: Any) -> NormalizedInput:
    """Return text with stable Unicode decoding and configured length metadata."""
    text, truncated = truncate_text(
        payload_to_text(payload),
        settings.SECURITY.max_text_input_chars,
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
    content, truncated = truncate_text(content, settings.SECURITY.max_text_input_chars)

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
    required_capability: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedInput:
    """
    Mark media that code-only normalization cannot faithfully convert.

    The next layer can route this to the configured media_expert instead of
    forcing lossy OCR/caption/transcription here. required_capability defaults
    to the modality, but callers can override it (e.g. a scanned PDF needs an
    image/vision-capable model for OCR, not a "pdf" capability).
    """
    handoff_metadata = {"handoff": "media_expert_required"}
    if metadata:
        handoff_metadata.update(metadata)

    return NormalizedInput(
        modality=modality,
        content_type=f"{modality}/native",
        native_payload=payload,
        target_layer=target_layer,
        target_provider=target_provider,
        target_model=target_model,
        preserved_native=False,
        requires_expert=True,
        required_capability=required_capability or modality,
        metadata=handoff_metadata,
    )


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
        if not normalized.content:
            # Image-only / scanned PDF: no text layer to extract. Route to an
            # OCR-capable expert instead of forwarding empty content (which the
            # verifier would otherwise reject as a broken handoff).
            normalized = _requires_expert(
                payload,
                Modality.PDF.value,
                target_layer,
                target_model.provider,
                target_model.model,
                required_capability="image",
                metadata={
                    "reason": "pdf has no extractable text layer (scanned/image-only)",
                    "pages": normalized.metadata.get("pages"),
                },
            )
    else:
        # Image/audio/video never go to the orchestrator's model — they are
        # routed to the MEDIA EXPERT. Judge native support against that route's
        # model, not the orchestrator's (issue #17: with an orchestrator model
        # that declares no media, every upload was marked requires_expert even
        # though the media route consumes it natively). The normalized target
        # follows the judging layer, so the verifier's coherence re-check
        # (verify_routing derives from target_layer) stays consistent.
        target_layer = "media_expert"
        target_model = registry.for_layer(target_layer)
        if target_model.supports(modality):
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
