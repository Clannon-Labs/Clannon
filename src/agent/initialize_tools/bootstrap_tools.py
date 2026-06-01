from pydantic_ai.agent import Agent

from registry.discovery import discover_registry_modules
from src.agent.initialize_tools.tool_adapter import ToolAdapter


def attach_registry_tools(agent: Agent) -> Agent:
    """
    One-line bootstrap function.

    This is your ONLY integration point.
    """

    discover_registry_modules()

    adapter = ToolAdapter(agent)
    adapter.register_all()

    return agent
