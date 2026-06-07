"""
Core pipeline entry point.

The pipeline is the spine of Vraksha. It declares the order a request travels
through and delegates all decisions to the stages themselves.

Current active flow:

    raw input
        -> intake      rate limit, size check, modality detection
        -> sanitizer   ClamAV/YARA pre-gate + modality sanitizer workers
        -> normalizer  code-only NormalizedInput construction
        -> verifier    structured safety/routing verification

Planned later stages:

    orchestrator  main agent reasoning, tools, experts, memory decisions
    output filter LLM + code output safety check
    output        final response formatting

Those planned stages are not imported here until their modules exist. Keeping
pipeline.py limited to active stages prevents import-time failures and makes the
current runnable path honest.
"""

from typing import Any

from foundation import Flow
from core import intake, normalizer, verifier, orchestrator
from security.sanitizers import runner as sanitizer


ACTIVE_STAGES = [
    intake.process,
    sanitizer.run,
    normalizer.run,
    verifier.run,
    orchestrator.run
]


async def run(raw_input: Any, session_id: str) -> Flow:
    """
    Run one user turn through the active Vraksha pipeline.

    Args:
        raw_input: Raw input exactly as received from the user. Intake owns
            size checks and modality detection, so callers should not normalize
            or sanitize before creating the pipeline.
        session_id: Session identifier used by Flow context and intake rate
            limiting.

    Returns:
        The final Flow from the active stage chain. If any stage blocks or
        fails, Flow.chain() skips the remaining stages automatically.
    """
    return await Flow.chain(
        Flow.new(raw_input, session_id),
        ACTIVE_STAGES
    )
