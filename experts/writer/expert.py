"""Writer/synthesis expert (key: synthesis.writer) — turns a task and gathered
findings into a clear, cited brief. Its prompt and skills live beside this file."""

from __future__ import annotations

from pydantic import BaseModel, Field

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class WriteIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(description="What to write, with any findings/context to synthesize.")


@expert
class WriterExpert:
    name = "writer"
    domain = "synthesis"
    description = "Synthesize a task (and any gathered findings) into a clear, cited brief."
    input_schema = WriteIn
    output_schema = ExpertOutput
    skills = ("skills",)       # the skills/ folder beside this file
    tools = ()                 # writer reasons over what it's given; no external tools
    model_role = "planner"
    tags = ("report", "writing", "citations")

    async def run(self, args: WriteIn, env: ExpertEnv) -> ExpertOutput:
        user_prompt = (
            f"Writing task: {args.prompt}\n\n"
            "Load a skill if it helps structure the piece. Then return ExpertOutput: "
            "a one-line summary, the full written brief as full_content, any sources "
            "you relied on in citations, and a confidence (0-1)."
        )
        return await think(env, user_prompt)
