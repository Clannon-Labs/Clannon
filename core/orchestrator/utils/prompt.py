"""
Compact per-turn prompt builder for the orchestrator advisor.

Keeps the advisor's context lean: the original request, a short memory-hydration
view, and prior brief observations/summaries only — never raw expert output. This
is the one place that decides what the advisor "sees" each turn.
"""

from __future__ import annotations

from typing import Any

from foundation import HydrationPackage, NormalizedInput, constants


def build_turn_prompt(
    normalized: NormalizedInput,
    hydration: HydrationPackage,
    observations: list[Any],
    turn: int,
    *,
    force_answer: bool = False,
) -> str:
    """Render the advisor prompt for one turn from the current loop state."""
    parts: list[str] = [
        f"User request (modality={normalized.modality}):",
        normalized.content or "[non-text payload]",
    ]

    if getattr(hydration, "items", None):
        parts.append("\nRelevant memory:")
        parts.extend(f"- ({item.store.value}) {item.content}" for item in hydration.items)

    if observations:
        parts.append("\nWork so far (summaries only):")
        parts.extend(f"- {_observation_text(o)}" for o in observations)

    parts.append(f"\nTurn {turn} of {constants.ORCHESTRATOR_MAX_TURNS}.")
    if force_answer:
        parts.append(
            "You MUST return kind='answer' with answer_text now. "
            "Do not request tools or experts."
        )
    else:
        parts.append("Decide the next action and return the structured decision schema.")

    return "\n".join(parts)


def _observation_text(observation: Any) -> str:
    """Render an ExpertSummary or a plain string observation as one line."""
    summary = getattr(observation, "summary", None)
    if summary is not None:
        return f"{getattr(observation, 'expert', 'expert')}: {summary}"
    return str(observation)
