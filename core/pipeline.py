import time

from foundation import Flow
from core import intake, normalizer, orchestrator, output
from security.verify import verifier
from security.sanitizer import runner as sanitizer
from security.filter import filter as output_filter


async def run(raw_input: any, session_id: str) -> Flow:
    """
        To run each layer one by one.
        This is the entire pipeline
    """
    return await(
        Flow.chain(
            Flow.new(raw_input, session_id),
            [
                intake.process, # Done
                sanitizer.run_parallel,
                normalizer.run,
                verifier.run,
                orchestrator.run,
                output_verifier.run,
                output.send,
            ]
        )
    )