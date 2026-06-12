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
    finding_refs: list[str] = Field(
        default_factory=list,
        description="Refs of earlier expert findings to synthesize from. The writer "
        "reads their FULL content — pass refs instead of restating research.",
    )


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
            f"Writing task: {args.prompt}\n"
            f"{_materials(args.finding_refs, env.findings)}\n"
            "Load a skill if it helps structure the piece. Then return ExpertOutput: "
            "a one-line summary, the full written piece as full_content, any sources "
            "you relied on in citations, and a confidence (0-1)."
        )
        return await think(env, user_prompt)


def _materials(refs: list[str], findings: list) -> str:
    """Inline the full content of the referenced findings as source material."""
    if not refs:
        return ""
    by_ref = {f.ref: f for f in findings}
    blocks: list[str] = []
    for ref in refs:
        found = by_ref.get(ref)
        if found is None:
            blocks.append(f"[finding {ref}: not available]")
            continue
        cites = ", ".join(found.citations) if found.citations else "none given"
        blocks.append(
            f"--- finding {ref} (from {found.expert}; sources: {cites}) ---\n"
            f"{found.full_content}"
        )
    return "\nSource material (full findings):\n\n" + "\n\n".join(blocks) + "\n"
