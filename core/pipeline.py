from foudation import BaseModel

class Pipeline:
    async def run(raw_input: object, session_id: str) -> Flow:
        return await Flow.chain(
            Flow.new(raw_input, session_id=session.id),
            [
            intake.process,
            sanitizer.run_parallel,
            normalizer.run,
            verifier.run,
            ochestrator.run,
            output_handler.run,
            output_filter.run,
            output_buffer.run
            ],
        )