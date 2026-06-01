"""Public prompt-helper surface for the agent runtime.

Top-level agent files import from here when they need prompt assembly logic but
should not own the assembly details themselves.
"""

from .governance_prompt import build_governance_prompt

__all__ = ["build_governance_prompt"]
