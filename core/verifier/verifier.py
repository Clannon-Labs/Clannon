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
    Origin,
    PipelineStage,
    VerifierError,
)

from .checks import verify_deterministic


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

    This first version is deterministic and fast. The function shape leaves a
    narrow place for a later structured LLM verifier without changing the
    pipeline contract or the orchestrator handoff.
    """
    started = time.monotonic()

    try:
        normalized = await flow.load()
        flow.ctx.advance(PipelineStage.VERIFYING)
        result = verify_deterministic(flow, normalized)

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

    except Exception as exc:
        return flow.fail(VerifierError(f"Verifier failed: {exc}"), Origin.VERIFIER, started)
