"""PydanticAI governance prompt registration.

This file directly touches the LLM runtime by registering `@agent.system_prompt`.
Supporting prompt assembly lives in `src.agent.prompting` so this boundary stays
small and easy to audit.
"""

from __future__ import annotations

from pydantic_ai.agent import Agent
from pydantic_ai.tools import RunContext

from src.agent.bootstrap import VrakshaDeps
from src.agent.prompting import build_governance_prompt


def register_governance_prompt(agent: Agent) -> None:
    """Attach Vraksha's governance/system prompt callback to a PydanticAI agent."""
    @agent.system_prompt
    async def apply_governance(context: RunContext[VrakshaDeps]) -> str:
        """PydanticAI callback that supplies the system prompt for each run."""
        return await build_governance_prompt(context)
