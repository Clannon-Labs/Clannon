"""Construct provider model instances after applying local credential config."""

from __future__ import annotations

import logging

from src.providers.config import normalize_provider
from src.providers.env import set_provider_env
from src.providers.imports import PROVIDERS_PRIORITY_ORDER
from src.utils.api_key_utils import get_api_key

logger = logging.getLogger(__name__)


def get_model_instance(provider_name: str, model_name: str):
    """Instantiate a provider model, or return None if setup fails."""
    provider_name = normalize_provider(provider_name)

    if provider_name not in ["ollama", "bedrock"]:
        key = get_api_key(provider_name)
        if not key or not key.strip():
            logger.warning("Key/Token for %s is ABSENT in ApiKeyStore.", provider_name)
            return None

        set_provider_env(provider_name, key)

    elif provider_name == "ollama":
        base_url = get_api_key("ollama")
        if base_url:
            set_provider_env("ollama", base_url)

    try:
        model_class = PROVIDERS_PRIORITY_ORDER.get(provider_name)
        if not model_class:
            logger.error("Provider '%s' is not supported or missing from registry.", provider_name)
            return None

        return model_class(model_name)

    except Exception as exc:
        logger.error("Provider %s failed to init model '%s': %s", provider_name, model_name, exc)
        return None
