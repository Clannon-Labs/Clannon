"""Web research expert (key: web.research) — searches the open web and returns
findings with sources. Its behavior lives in its system prompt + skills beside this
file; this module declares what it is, what it needs, and how its input becomes the
agent's task."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class ResearchIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(description="The research question or task to investigate.")


@expert
class WebResearchExpert:
    name = "research"
    domain = "web"
    description = "Research a question on the open web and return findings with source URLs."
    input_schema = ResearchIn
    output_schema = ExpertOutput
    skills = ("skills",)                       # baseline skills/ beside this file
    tools = ("search.web", "web.fetch_url")    # REQUESTED; the handler grants them (scoped, guarded)
    model_role = "research"
    permission = PermissionLevel.NETWORK
    tags = ("open-web", "sources", "citations")

    async def run(self, args: ResearchIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: ResearchIn, env: ExpertEnv) -> str:
    """Build this expert's per-call task text from its structured input. The task IS
    the research question; the behavior (search/read/cross-check) lives in the
    system prompt."""
    return args.prompt
