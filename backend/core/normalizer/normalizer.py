"""
Code-only input normalizer — the layer's entry point.

The normalizer receives the sanitized payload from the sanitizer layer and turns
it into a structured handoff for later LLM/tool stages. It does not call an LLM.
This file is the stage door: it picks the modality off the context, delegates the
actual normalization to `builders.normalize_payload`, stores the result, and
hands the Flow forward. The normalization logic lives in `builders.py`.
"""

from __future__ import annotations

import time

from foundation import (
    Flow,
    Modality,
    Origin,
    PipelineStage,
)

from .builders import normalize_payload


def _primary_modality(flow: Flow) -> str:
    """Return the first detected modality, falling back to text."""
    if flow.ctx.detected_modalities:
        return flow.ctx.detected_modalities[0]
    return Modality.TEXT.value


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
