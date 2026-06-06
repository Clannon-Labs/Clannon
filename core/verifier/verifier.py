"""
Verifier stage entry point.

The verifier receives the current Flow payload from the normalizer, writes a
structured VerificationResult to flow.ctx, then returns next/block/warn/fail.
Detailed handoff, routing, and text-risk checks live in sibling modules.
"""

from __future__ import annotations

import time
from typing import Any

from foundation import (
    BlockReason,
    Flow,
    ModelUnavailableError,
    NormalizedInput,
    Origin,
    PipelineStage,
    VerifierError,
)

from .agent import verify_with_llm
from .checks import verify_deterministic
from .constants import TEXT_MODALITIES


def _block_reason(categories: list[str]) -> BlockReason:
    """Map internal verifier categories to pipeline block reasons."""
    if "unsupported_modality" in categories:
        return BlockReason.UNSUPPORTED_MODALITY

    injection_categories = {
        "prompt_injection",
        "prompt_exfiltration",
        "jailbreak",
    }
    if injection_categories.intersection(categories):
        return BlockReason.INJECTION_DETECTED

    return BlockReason.VERIFIER_REJECTED


async def run(flow: Flow[Any]) -> Flow[Any]:
    """
    Pipeline entry point for verification.

    Deterministic checks run first for speed and hard handoff validation. The
    regex pass is only a hint — every text/PDF input that clears the structural
    checks is then adjudicated by the structured verifier LLM, which is the sole
    content-blocker before the orchestrator. (result.proceed is False here only
    when a structural gate already blocked, e.g. unsupported modality.)
    """
    started = time.monotonic()

    try:
        normalized = await flow.load()
        flow.ctx.advance(PipelineStage.VERIFYING)
        result = verify_deterministic(flow, normalized)

        if (
            isinstance(normalized, NormalizedInput)
            and normalized.modality in TEXT_MODALITIES
            and normalized.content
            and result.proceed
        ):
            result = await verify_with_llm(normalized, result)

        flow.ctx.verifier_result = result

        if not result.proceed or result.dangerous or result.threat_level.should_block:
            flow.ctx.verifier_blocked = True
            flow.ctx.verifier_block_reason = result.reason
            return flow.block(
                _block_reason(result.categories),
                result.threat_level,
                Origin.VERIFIER,
                started,
            )

        flow.ctx.verifier_blocked = False
        flow.ctx.verifier_block_reason = result.reason

        if result.warn or result.threat_level.should_warn:
            return flow.warn(
                result.reason or "Verifier warning",
                result.threat_level,
                Origin.VERIFIER,
                started,
            )

        return flow.next(normalized, Origin.VERIFIER, started)

    except VerifierError as exc:
        return flow.fail(exc, Origin.VERIFIER, started)

    except ModelUnavailableError as exc:
        return flow.fail(exc, Origin.VERIFIER, started)

    except Exception as exc:
        return flow.fail(VerifierError(f"Verifier failed: {exc}"), Origin.VERIFIER, started)
