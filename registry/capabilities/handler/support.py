"""
Expert support: the mini-environment an expert runs in, plus the helpers that
load its skills and call its model. Kept in one file because these are small and
only the expert handler and the expert classes use them.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path

from foundation import ToolCallRecord, constants
from core.llm import build_agent, run_structured

from ..schemas import ExpertOutput, ToolRequest


class ScopedToolbox:
    """A by-key tool caller handed to an expert, restricted to its granted tools.

    Calls go through the (already scoped) tool handler against the real ctx, so an
    expert's tool calls are recorded on ctx.tool_calls like any other.
    """

    def __init__(self, handler, ctx) -> None:
        self._handler = handler
        self._ctx = ctx

    async def call(self, key: str, **arguments) -> ToolCallRecord:
        return await self._handler.call_tool(ToolRequest(key=key, arguments=arguments), self._ctx)


@dataclass
class ExpertEnv:
    """What an expert.run(task, env) receives — its scoped, self-contained context."""
    prompt_name: str
    model_role: str
    skills: str = ""
    tools: ScopedToolbox | None = None


def load_skills(impl_cls: type, skill_files: tuple[str, ...]) -> str:
    """Concatenate the named skill files found in the expert's skills/ directory."""
    base = Path(inspect.getfile(impl_cls)).parent / "skills"
    parts: list[str] = []
    for name in skill_files:
        path = base / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


async def think(env: ExpertEnv, user_prompt: str) -> ExpertOutput:
    """Run the expert's model (role + system prompt from env) for an ExpertOutput."""
    handle = build_agent(
        env.model_role,
        output_type=ExpertOutput,
        prompt_name=env.prompt_name,
        retries=constants.ORCHESTRATOR_MAX_RETRIES,
    )
    composed = (f"Your skills:\n{env.skills}\n\n" if env.skills else "") + user_prompt
    return await run_structured(handle, composed)
