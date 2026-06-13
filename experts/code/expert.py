"""Code expert (key: code.engineer) — reads, writes, refactors, debugs, and
explains code, and runs Python to test it. Its behavior lives in its system prompt +
skills beside this file; this module declares what it is and how its input becomes
the agent's task."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class CodeIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(description="The coding task, with any existing code or context to work from, inline.")


@expert
class CodeExpert:
    name = "engineer"
    domain = "code"
    description = "Write, refactor, debug, and explain code, running Python to test it where useful."
    input_schema = CodeIn
    output_schema = ExpertOutput
    skills = ("skills",)               # baseline skills/ beside this file
    tools = ("code.python_exec",)      # REQUESTED; the handler grants it (scoped, guarded)
    model_role = "code"
    permission = PermissionLevel.EXECUTE
    tags = ("code", "debugging", "tests")

    async def run(self, args: CodeIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: CodeIn, env: ExpertEnv) -> str:
    """Build this expert's per-call task from the coding request."""
    return args.prompt
