"""Environment-variable helpers for provider runtime configuration."""

from __future__ import annotations

import os

from src.utils.api_key_utils import get_api_key

PYDANTIC_AI_ENV_MAPPING = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "xai": ("XAI_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "cohere": ("CO_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "cerebras": ("CEREBRAS_API_KEY",),
    "huggingface": ("HF_TOKEN",),
    "ollama": ("OLLAMA_BASE_URL",),
}


def set_provider_env(provider_name: str, value: str) -> None:
    """Expose a resolved provider credential under the env var expected by SDKs."""
    for target_env in PYDANTIC_AI_ENV_MAPPING.get(provider_name, ()):
        os.environ[target_env] = value.strip()


def provider_has_runtime_config(provider_name: str) -> bool:
    """Return whether a provider has enough local configuration to be attempted."""
    if provider_name == "bedrock":
        return bool(
            get_api_key("bedrock")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or os.getenv("AWS_PROFILE")
        )

    return bool(get_api_key(provider_name))
