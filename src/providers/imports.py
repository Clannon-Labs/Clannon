from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

try:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.models.bedrock import BedrockConverseModel
    from pydantic_ai.models.cerebras import CerebrasModel
    from pydantic_ai.models.cohere import CohereModel
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.models.groq import GroqModel
    from pydantic_ai.models.huggingface import HuggingFaceModel
    from pydantic_ai.models.mistral import MistralModel
    from pydantic_ai.models.ollama import OllamaModel
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.models.xai import XaiModel
except ImportError as exc:
    logger.warning("VRAKSHA ENGINE ERROR: PydanticAI components missing.")
    print("\n\033[38;5;203m[!] VRAKSHA ENGINE ERROR: PydanticAI components missing.\033[0m")
    print(f"Details: {exc}")
    print("If you are in Docker, please run: \033[38;5;111mvraksha build\033[0m")
    print("If you are in venv, please run: \033[38;5;111mpip install -r requirements.txt\033[0m")
    sys.exit(1)


PROVIDERS_PRIORITY_ORDER = {
    "google": GoogleModel,
    "openrouter": OpenRouterModel,
    "ollama": OllamaModel,
    "anthropic": AnthropicModel,
    "openai": OpenAIChatModel,
    "xai": XaiModel,
    "mistral": MistralModel,
    "cohere": CohereModel,
    "groq": GroqModel,
    "huggingface": HuggingFaceModel,
    "cerebras": CerebrasModel,
    "bedrock": BedrockConverseModel,
}
