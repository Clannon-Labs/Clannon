"""
The orchestrator's user-message builder.

The orchestrator is a native tool-driving agent now: its available tools/experts
are real tool schemas (not prose in the prompt), and it runs its own tool loop —
so this is just the per-turn *content*: the user's request plus a short
memory-hydration view. Capabilities are NOT listed here.
"""

from __future__ import annotations

import time

from foundation import HydrationPackage, NormalizedInput


def _age(created_at: float) -> str:
    """A short 'learned when' hint for a memory item — provenance the model can
    use to weigh recency. Empty when unknown (text/wiki tier carries no ts)."""
    if not created_at:
        return ""
    days = (time.time() - created_at) / 86_400
    if days < 1:
        return ", today"
    if days < 2:
        return ", yesterday"
    return f", {int(days)}d ago"


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

    files = [f for f in (input_files or []) if getattr(f, "name", None)]
    if files:
        listed = ", ".join(f"{f.name} ({getattr(f, 'modality', '?')})" for f in files)
        parts.append(
            "\nThe user attached input files for this task: " + listed + ". They are "
            "available only inside a file-capable expert's workspace, so you MUST delegate "
            "to read them. Route by modality: images, audio, video, and PDF documents go to "
            "the media expert (it reads them with a multimodal model); data and code files "
            "(CSV, JSON, plain text, source) go to data analysis or code. Do not try to read "
            "a file's contents yourself."
        )

    if getattr(hydration, "items", None):
        parts.append("\nRelevant memory:")
        parts.extend(
            f"- ({item.store.value}{_age(getattr(item, 'created_at', 0.0))}) {item.content}"
            for item in hydration.items
        )

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
