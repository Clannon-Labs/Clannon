"""
factory/assemble.py
───────────────────
The prompt factory. One job: accept runtime context, return a ready-to-inject
system prompt string. Engine and bootstrap both call this — nothing else builds prompts.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from src.factory.build.system_prompt import (
    DEFAULT_SOUL,
    BASELINE_RULES,
    MEMORY_GUIDANCE,
    TOOL_USE_GUIDANCE,
)

if TYPE_CHECKING:
    pass  # reserved for future typed context objects


def build_system_prompt(
    *,
    soul: str | None = None,
    rules: str | None = None,
    essential_context: str = "",
) -> str:
    """
    Assemble the final system prompt string from its constituent blocks.

    Args:
        soul:              Identity block. Falls back to DEFAULT_SOUL if None/empty.
        rules:             Governance block. Falls back to BASELINE_RULES if None/empty.
        essential_context: Live memory context injected per-session (optional).

    Returns:
        A single, ready-to-inject system prompt string.
    """
    resolved_soul  = (soul  or "").strip() or DEFAULT_SOUL.strip()
    resolved_rules = (rules or "").strip() or BASELINE_RULES.strip()

    sections: list[str] = [
        f"# SYSTEM RULES (IMMUTABLE)\n{resolved_rules}",
        f"# YOUR IDENTITY (SOUL)\n{resolved_soul}",
        f"# MEMORY GUIDANCE\n{MEMORY_GUIDANCE}",
        f"# TOOL-USE ENFORCEMENT\n{TOOL_USE_GUIDANCE}",
    ]

    if essential_context.strip():
        sections.append(f"# RELEVANT CONTEXT (LIVE MEMORY)\n{essential_context.strip()}")

    return "\n\n".join(sections)