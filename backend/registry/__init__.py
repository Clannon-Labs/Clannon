"""Vraksha registry: the single place anything gets registered.

Config (models, prompts) is foundation-level; capabilities (tools, experts) and
their handler are core-level. Import the decorators and config loaders from here;
the capability handler lives under registry.capabilities.handler.
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
