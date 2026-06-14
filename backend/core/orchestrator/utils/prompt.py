"""
The orchestrator's user-message builder.

The orchestrator is a native tool-driving agent now: its available tools/experts
are real tool schemas (not prose in the prompt), and it runs its own tool loop —
so this is just the per-turn *content*: the user's request plus a short
memory-hydration view. Capabilities are NOT listed here.
"""

from __future__ import annotations

from foundation import HydrationPackage, NormalizedInput


def build_user_prompt(
    normalized: NormalizedInput,
    hydration: HydrationPackage,
    revision_feedback: str | None = None,
    input_files: list | None = None,
) -> str:
    """Render the orchestrator's user message: the request + relevant memory.

    `revision_feedback` is set only on a retry after the output filter rejected
    the previous draft — it tells the orchestrator what to fix and try again.
    `input_files` are uploaded files admitted for this run (foundation.InputFile);
    naming them tells the orchestrator to delegate to a file-capable expert."""
    parts: list[str] = [
        f"User request (modality={normalized.modality}):",
        normalized.content or "[non-text payload]",
    ]

    names = [getattr(f, "name", None) for f in (input_files or [])]
    names = [n for n in names if n]
    if names:
        parts.append(
            "\nThe user attached input files for this task: "
            + ", ".join(names)
            + ". They are available only inside a file-capable expert's workspace — "
            "delegate to the right expert (e.g. data analysis or code) to read and use them."
        )

    if getattr(hydration, "items", None):
        parts.append("\nRelevant memory:")
        parts.extend(f"- ({item.store.value}) {item.content}" for item in hydration.items)

    if revision_feedback:
        parts.append(
            "\nYour previous draft was REJECTED by the output safety/quality filter "
            f"for this reason:\n{revision_feedback}\n"
            "Produce a corrected answer that addresses it — ground every claim in the "
            "findings, drop anything unsupported, and remove any unsafe content. Do not "
            "repeat the rejected version."
        )

    parts.append(
        "\nUse your tools and experts as needed, then return your final answer."
    )
    return "\n".join(parts)
