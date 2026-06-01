from __future__ import annotations

import os

from src.utils.api_key_utils.aliases import normalize_provider_name


class ApiKeyStore:
    def __init__(self, schema: dict):
        self.schema = schema
        self._keys = {}
        self._sources = {}

    def load_keys(self) -> None:
        keys = {}
        sources = {}

        for provider, env_vars in self.schema.items():
            provider = normalize_provider_name(provider)
            value = None
            source = None

            for env_var in env_vars:
                value = os.getenv(env_var)
                if value:
                    source = env_var
                    break

            keys[provider] = value
            sources[provider] = source

        self._keys = keys
        self._sources = sources

    def get_key(self, provider: str):
        return self._keys.get(normalize_provider_name(provider))

    def get_source(self, provider: str):
        return self._sources.get(normalize_provider_name(provider))
