from __future__ import annotations

from pydantic_ai.agent import Agent
from pydantic_ai.models.test import TestModel

from src.agent.bootstrap import VrakshaDeps
from src.agent.governance import register_governance_prompt
from src.agent.initialize_tools.bootstrap_tools import attach_registry_tools


def create_vraksha_agent() -> Agent:
    agent = Agent(
        TestModel(),
        deps_type=VrakshaDeps,
    )
    attach_registry_tools(agent)
    register_governance_prompt(agent)
    return agent


vraksha_agent = create_vraksha_agent()
