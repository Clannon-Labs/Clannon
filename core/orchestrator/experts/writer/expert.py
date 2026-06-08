"""Writer/synthesis expert (key: synthesis.writer) — turns a task and gathered
findings into a clear, cited brief."""

from __future__ import annotations

from ...registry import expert
from ...schemas import ExpertOutput
from ..support import ExpertEnv, think


@expert(
    name="writer",
    domain="synthesis",
    description="Synthesize a task (and any gathered findings) into a clear, cited brief.",
    prompt_name="experts/writer",
    output_schema=ExpertOutput,
    skills=("brief_structure.md",),
    tools=(),
    model_role="planner",
    tags=("report", "writing", "citations"),
)
class WriterExpert:
    async def run(self, task: str, env: ExpertEnv) -> ExpertOutput:
        user_prompt = (
            f"Writing task: {task}\n\n"
            "Return ExpertOutput: a one-line summary, the full written brief as "
            "full_content, any sources you relied on in citations, and a confidence (0-1)."
        )
        return await think(env, user_prompt)
