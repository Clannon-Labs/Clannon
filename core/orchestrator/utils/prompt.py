"""
The orchestrator's user-message builder.

The orchestrator is a native tool-driving agent now: its available tools/experts
are real tool schemas (not prose in the prompt), and it runs its own tool loop —
so this is just the per-turn *content*: the user's request plus a short
memory-hydration view. Capabilities are NOT listed here.
"""

from __future__ import annotations

from foundation import HydrationPackage, NormalizedInput


def build_user_prompt(normalized: NormalizedInput, hydration: HydrationPackage) -> str:
    """Render the orchestrator's user message: the request + relevant memory."""
    parts: list[str] = [
        f"User request (modality={normalized.modality}):",
        normalized.content or "[non-text payload]",
    ]

    if getattr(hydration, "items", None):
        parts.append("\nRelevant memory:")
        parts.extend(f"- ({item.store.value}) {item.content}" for item in hydration.items)

    parts.append(
        "\nUse your tools and experts as needed, then return your final answer."
    )
    return "\n".join(parts)
