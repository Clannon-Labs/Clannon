"""Data-analysis expert (key: data.analyst) — analyzes structured data (CSV, JSON,
tabular text) in the sandboxed workspace: writes the data and an analysis script,
runs it, and reports trends, outliers, and statistics as tables. Its behavior lives
in its system prompt + skills beside this file; this module declares what it is and
how its input becomes the agent's task."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class DataAnalysisIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(description="The analysis question or task, with the data (CSV/JSON/tabular) to analyze inline.")


@expert
class DataAnalysisExpert:
    name = "analyst"
    domain = "data"
    description = "Analyze structured data (CSV/JSON/tabular): summarize, find trends and outliers, run statistics, and report as tables."
    input_schema = DataAnalysisIn
    output_schema = ExpertOutput
    skills = ("skills",)               # baseline skills/ beside this file
    tools = ("fs.read", "fs.write", "code.run")  # REQUESTED; grants a per-run sandboxed workspace
    model_role = "code"                # writes pandas/numpy analysis code
    permission = PermissionLevel.EXECUTE
    tags = ("data", "analysis", "statistics")

    async def run(self, args: DataAnalysisIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: DataAnalysisIn, env: ExpertEnv) -> str:
    """Build this expert's per-call task from the analysis request (data inline)."""
    return args.prompt
