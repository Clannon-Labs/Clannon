"""Summarization expert (key: summary.condenser) — condenses long content (transcripts,
long documents, research dumps, threads) into a digestible form at the length and shape
the caller asks for, without losing the load-bearing facts. Pure reasoning: the content
to condense arrives inline; no tools. Its behavior lives in its system prompt + skills
beside this file; this module declares what it is and how its request becomes the task."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class SummaryIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(
        description="The content to summarize, inline, plus how to condense it: the target "
        "length or format (e.g. one paragraph, 5 bullets, an executive summary) and what to "
        "focus on or preserve."
    )


@expert
class SummarizationExpert:
    name = "condenser"
    domain = "summary"
    description = (
        "Condense long content (transcripts, documents, research dumps, threads) into a "
        "digestible summary at the requested length and shape, preserving the key facts, "
        "decisions, and numbers without adding anything."
    )
    input_schema = SummaryIn
    output_schema = ExpertOutput
    skills = ("skills",)               # baseline skills/ beside this file
    tools = ()                         # pure reasoning: the content arrives inline, no tools
    model_role = "research"            # general text condensation
    permission = PermissionLevel.READ
    tags = ("summarization", "condense", "tldr")

    async def run(self, args: SummaryIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: SummaryIn, env: ExpertEnv) -> str:
    """This expert's per-call task: the content to condense + how, inline."""
    return args.prompt
