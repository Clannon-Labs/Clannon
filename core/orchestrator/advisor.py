"""
The advisor: the orchestrator's bridge to the model.

The model is an ADVISOR, not the driver. Each turn the advisor builds a compact
prompt from the loop state and asks for one structured `OrchestratorDecision`;
Vraksha's loop decides what to actually do with it. All SDK access goes through
the core/llm framework adapter, so this module never imports pydantic_ai.
"""

from __future__ import annotations

from typing import Any

from foundation import HydrationPackage, NormalizedInput, constants
from core.llm import build_agent, run_structured

from .schemas import OrchestratorDecision
from .utils.prompt import build_turn_prompt


async def decide(
    normalized: NormalizedInput,
    hydration: HydrationPackage,
    observations: list[Any],
    turn: int,
    *,
    force_answer: bool = False,
) -> OrchestratorDecision:
    """Ask the advisor for the next structured decision given the current state."""
    prompt = build_turn_prompt(normalized, hydration, observations, turn, force_answer=force_answer)
    handle = build_agent(
        "orchestrator",
        output_type=OrchestratorDecision,
        prompt_name="orchestrator",
        retries=constants.ORCHESTRATOR_MAX_RETRIES,
    )
    return await run_structured(handle, prompt)
