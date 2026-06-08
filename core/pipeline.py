"""
Core pipeline entry point.

The pipeline is the spine of Vraksha. It declares the order a request travels
through and delegates all decisions to the stages themselves.

Current active flow:

    raw input
        -> intake        rate limit, size check, modality detection
        -> sanitizer     ClamAV/YARA pre-gate + modality sanitizer workers
        -> normalizer    code-only NormalizedInput construction
        -> verifier      structured safety/routing verification
        -> orchestrator  Vraksha-owned reasoning loop (experts + tools + memory)
        -> output filter structured safety/groundedness gate on the draft
        -> delivery      sets final_response and delivers (CLI today)

Delivery is the current terminal stage. Each stage takes and returns a Flow; a
block or fail short-circuits the rest via Flow.chain().
"""

from typing import Any

from foundation import Flow
from core import intake, normalizer, verifier, orchestrator
from security.sanitizers import runner as sanitizer
from security.filter import run as output_filter_run
from delivery import run as delivery_run


ACTIVE_STAGES = [
    intake.process,
    sanitizer.run,
    normalizer.run,
    verifier.run,
    orchestrator.run,
    output_filter_run,
    delivery_run
]


async def run(raw_input: Any, session_id: str, user_id: str = "local-user") -> Flow:
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
        Flow.new(raw_input, session_id, user_id=user_id),
        ACTIVE_STAGES
    )
