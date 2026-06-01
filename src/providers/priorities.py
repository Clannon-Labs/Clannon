"""Build ordered model candidates for a task from config and available keys."""

from __future__ import annotations

import logging

from src.providers.candidate import ModelCandidate
from src.providers.config import load_model_config
from src.providers.defaults import DEFAULT_MODELS
from src.providers.env import provider_has_runtime_config
from src.providers.imports import PROVIDERS_PRIORITY_ORDER
from src.utils.api_key_utils import get_api_key_source

logger = logging.getLogger(__name__)


def get_model_priorities(task: str):
    """Return configured model candidates that have usable runtime credentials."""
    config = load_model_config()
    candidates = []

    for provider_name in PROVIDERS_PRIORITY_ORDER.keys():
        if not provider_has_runtime_config(provider_name):
            logger.debug("Provider %s is not configured; skipping.", provider_name)
            continue

        provider_config = config.get(provider_name, {})

        if isinstance(provider_config, dict):
            task_entry = provider_config.get(task)
            model_name = task_entry.get("model") if isinstance(task_entry, dict) else task_entry
        else:
            model_name = None

        if not model_name:
            task_defaults = DEFAULT_MODELS.get(provider_name, {})
            model_name = task_defaults.get(task) or task_defaults.get("orchestrator", "unknown")

        if model_name and model_name != "unknown":
            key_source = get_api_key_source(provider_name)
            if key_source:
                logger.debug("Provider %s configured from %s.", provider_name, key_source)
            candidates.append(ModelCandidate(provider_name, model_name))

    return candidates
