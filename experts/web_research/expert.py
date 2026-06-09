"""Web research expert (key: research.web_research) — searches the open web and
returns findings with sources."""

from __future__ import annotations

from foundation import PermissionLevel

from ...registry import expert
from ...schemas import ExpertOutput
from ..support import ExpertEnv, think


@expert(
    name="web_research",
    domain="research",
    description="Research a question on the open web and return findings with source URLs.",
    prompt_name="experts/web_research",
    output_schema=ExpertOutput,
    skills=("source_eval.md",),
    tools=("search.web", "web.fetch_url"),
    model_role="research",
    tags=("open-web", "sources", "citations"),
    permission=PermissionLevel.NETWORK,
)
class WebResearchExpert:
    async def run(self, task: str, env: ExpertEnv) -> ExpertOutput:
        gathered = "(no web results available)"
        if env.tools is not None:
            record = await env.tools.call("search.web", query=task)
            if record.success and record.result:
                gathered = record.result.get("findings", gathered)

        user_prompt = (
            f"Research task: {task}\n\n"
            f"Web findings:\n{gathered}\n\n"
            "Return ExpertOutput: a brief 1-2 sentence summary, the full findings as "
            "full_content with any source URLs listed in citations, and a confidence (0-1)."
        )
        return await think(env, user_prompt)
