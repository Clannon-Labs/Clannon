"""Prompt construction helpers used by the agent governance boundary.

The actual PydanticAI registration stays in `src.agent.governance`; this module
does the pure assembly work it calls so LLM-boundary code remains small.
"""

from __future__ import annotations

from pydantic_ai.tools import RunContext

from src.agent.bootstrap import VrakshaDeps
from src.agent.memory import AgentMemory
from src.factory.assemble import build_system_prompt


async def build_governance_prompt(context: RunContext[VrakshaDeps]) -> str:
    """Build the system prompt from identity, rules, and agent memory context."""
    essential_context = await AgentMemory(context.deps.memory).essential_context()

    return build_system_prompt(
        soul=context.deps.soul,
        rules=context.deps.rules,
        essential_context=essential_context,
    )
