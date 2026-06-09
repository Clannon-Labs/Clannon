"""Web research expert (key: research.web_research) — searches the open web and
returns findings with sources. Its prompt and skills live beside this file."""

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
    skills = ("skills",)                       # the skills/ folder beside this file
    tools = ("search.web", "web.fetch_url")    # may call these (model-driven, guarded)
    model_role = "research"
    permission = PermissionLevel.NETWORK
    tags = ("open-web", "sources", "citations")

    async def run(self, args: ResearchIn, env: ExpertEnv) -> ExpertOutput:
        user_prompt = (
            f"Research task: {args.prompt}\n\n"
            "Use your tools to search the web and fetch pages for sources, and load "
            "a skill if it helps. Then return ExpertOutput: a 1-2 sentence summary, "
            "the full findings as full_content with source URLs in citations, and a "
            "confidence (0-1)."
        )
        return await think(env, user_prompt)
