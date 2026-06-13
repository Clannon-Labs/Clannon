"""
The capability handler: the `Capabilities` gateway (which builds & runs the native
tool-driving orchestrator turn) plus the tool/expert engines it wraps and the
expert run-environment helpers.

Core-level (depends on core.llm + security), so it is NOT imported by the light
registry surfaces (registry/__init__, registry.capabilities/__init__) — import it
explicitly from here when you need to run capabilities or build an expert.
"""

from .capability import Capabilities
from .experts import ExpertHandler
from .tools import ToolHandler
from .support import (
    ExpertDeps,
    ExpertEnv,
    ScopedToolbox,
    SkillBook,
    build_expert_tools,
    load_skill,
    skills_hint,
    think,
)

__all__ = [
    "Capabilities",
    "ToolHandler",
    "ExpertHandler",
    "ExpertDeps",
    "ExpertEnv",
    "ScopedToolbox",
    "SkillBook",
    "build_expert_tools",
    "load_skill",
    "skills_hint",
    "think",
]
