"""Load and normalize provider model configuration."""

from __future__ import annotations

import logging

import yaml

from get_root import root
from src.providers.defaults import DEFAULT_MODELS
from src.utils.api_key_utils import normalize_provider_name

logger = logging.getLogger(__name__)

CONFIG_PATH = root.project / "models.yaml"


def normalize_provider(provider_name: str) -> str:
    """Normalize provider aliases to the canonical provider key."""
    return normalize_provider_name(provider_name)


def normalize_model_config(config: dict) -> dict:
    """Return model config with provider aliases collapsed to canonical names."""
    normalized = {}

    for provider_name, provider_config in config.items():
        canonical_name = normalize_provider(provider_name)

        if canonical_name in normalized:
            logger.warning(
                "Duplicate model config for provider alias '%s'; keeping earlier '%s' config.",
                provider_name,
                canonical_name,
            )
            continue

        normalized[canonical_name] = provider_config

    return normalized


def load_model_config() -> dict:
    """Load `models.yaml`, falling back to bundled defaults when needed."""
    if not CONFIG_PATH.exists():
        return normalize_model_config(DEFAULT_MODELS)

    try:
        with open(CONFIG_PATH, "r") as file:
            config = yaml.safe_load(file) or DEFAULT_MODELS

        if not isinstance(config, dict):
            logger.warning("models.yaml did not contain a provider map; using defaults...")
            return normalize_model_config(DEFAULT_MODELS)

        return normalize_model_config(config)

    except Exception as exc:
        logger.warning("Failed to load models.yaml (%s), using defaults...", exc)
        return normalize_model_config(DEFAULT_MODELS)
