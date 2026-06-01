"""Runtime API-key lookup for model providers.

This module owns the process-wide key store used by provider selection and
model construction. Keeping the mutable store here avoids a compatibility
facade and gives the rest of the codebase one clear import path for credentials.
"""

from __future__ import annotations

from src.utils.api_key_utils.env_loader import init_env
from src.utils.api_key_utils.schema import PROVIDER_KEY_SCHEMA
from src.utils.api_key_utils.store import ApiKeyStore

init_env()

key_store = ApiKeyStore(PROVIDER_KEY_SCHEMA)
key_store.load_keys()


def get_api_key(provider: str) -> str:
    """Return the configured secret value for a provider alias or canonical name."""
    return key_store.get_key(provider)


def get_api_key_source(provider: str) -> str:
    """Return the environment variable that supplied a provider key, if any."""
    return key_store.get_source(provider)
