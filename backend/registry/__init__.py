"""Vraksha registry: the single place anything gets registered.

Two buckets live here: config loaders (models, prompts) in `registry.config` —
the base tier, imported directly by config consumers — and capabilities (tools,
experts) plus their handler in `registry.capabilities`. Import the decorators and
config loaders from here; the capability handler lives under
registry.capabilities.handler.
"""

from .config import (
    ModelProfile,
    ModelRegistry,
    load_model_registry,
    Prompt,
    PromptRegistry,
    get_prompt,
    load_prompt_registry,
)
from .capabilities import tool, expert

__all__ = [
    "tool",
    "expert",
    "ModelProfile",
    "ModelRegistry",
    "load_model_registry",
    "Prompt",
    "PromptRegistry",
    "get_prompt",
    "load_prompt_registry",
]
