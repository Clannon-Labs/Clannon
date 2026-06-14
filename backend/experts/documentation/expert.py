"""Documentation expert (key: docs.writer) — writes and structures documents:
technical docs, product/design specs, API docs, changelogs, decision records,
READMEs. It reads any existing/attached docs first (to stay consistent in voice,
structure, and terminology), writes the document into its workspace, and delivers
it as a file artifact. Its behavior lives in its system prompt + skills beside this
file; this module declares what it is and how its request becomes the agent's task."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class DocsIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(
        description="The document to write: what kind (spec, README, API doc, changelog, "
        "decision record, ...), who it's for, and the source material or requirements to "
        "base it on, inline. Any existing doc to update or match is attached as a file."
    )


@expert
class DocumentationExpert:
    name = "writer"
    domain = "docs"
    description = (
        "Write and structure documents (specs, READMEs, API docs, changelogs, decision "
        "records): read any existing/attached docs first to stay consistent, then write a "
        "clear, well-structured document and deliver it as a file."
    )
    input_schema = DocsIn
    output_schema = ExpertOutput
    skills = ("skills",)                       # baseline skills/ beside this file
    tools = ("fs.read", "fs.write")            # read attached source docs, write + deliver the doc
    model_role = "planner"                     # long-form structured writing
    permission = PermissionLevel.WRITE
    tags = ("documentation", "writing", "specs", "readme")

    async def run(self, args: DocsIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: DocsIn, env: ExpertEnv) -> str:
    """This expert's per-call task: the documentation request (source material inline)."""
    return args.prompt
