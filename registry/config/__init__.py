"""Foundation-level config loaders: model routing (models.yaml) and prompt
resolution (prompts/). Depend only on foundation."""

from .models import ModelProfile, ModelRegistry, load_model_registry
from .prompts import Prompt, PromptRegistry, get_prompt, load_prompt_registry

__all__ = [
    "ModelProfile",
    "ModelRegistry",
    "load_model_registry",
    "Prompt",
    "PromptRegistry",
    "get_prompt",
    "load_prompt_registry",
]
