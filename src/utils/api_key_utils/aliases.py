from __future__ import annotations

PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "openai": "openai",
    "chatgpt": "openai",
    "gpt": "openai",
    "google": "google",
    "gemini": "google",
    "xai": "xai",
    "x": "xai",
    "grok": "xai",
    "twitter": "xai",
    "openrouter": "openrouter",
    "open_router": "openrouter",
    "mistral": "mistral",
    "bedrock": "bedrock",
    "aws_bedrock": "bedrock",
    "cerebras": "cerebras",
    "cohere": "cohere",
    "groq": "groq",
    "ollama": "ollama",
    "huggingface": "huggingface",
    "hugging_face": "huggingface",
    "hf": "huggingface",
    "github": "github",
    "gh": "github",
}


def normalize_provider_name(provider: str) -> str:
    normalized = provider.lower().strip().replace("-", "_").replace(" ", "_")
    return PROVIDER_ALIASES.get(normalized, normalized)
