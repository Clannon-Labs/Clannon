"""CLI loop entrypoint for the central agent.

This file connects the older terminal loop to the current agent bridge. It does
not own orchestration logic; it only wires user input into the runtime path.
"""

from src.agent.bridge import agent_bridge as agent
from src.utils.base_loop import run_loop


def run_agent():
    """Start the interactive terminal loop backed by the Vraksha agent bridge."""
    run_loop(
        title="CORE AGENT",
        input_prompt="Ask something",
        llm_fn=agent,
        verify_always=False,
    )

    
