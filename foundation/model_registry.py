"""
Model registry loaded from the root models.yaml file.

Every LLM-using layer should resolve models through this module instead of
hardcoding provider/model names. The normalizer can also use the registry to
decide whether a target layer's model can receive native media or needs a
code/tool based conversion first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_MODELS_PATH = Path(__file__).resolve().parents[1] / "models.yaml"
DEFAULT_PROVIDER_ENV = "VRAKSHA_MODEL_PROVIDER"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """Resolved model configuration for one provider + role/layer."""
    provider: str
    role: str
    model: str
    task: str | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    settings: dict[str, Any] = field(default_factory=dict)

    def supports(self, capability: str) -> bool:
        """Return True when this model declares the requested capability."""
        return capability in self.capabilities


class ModelRegistry:
    """
    Reads root model configuration and resolves role-specific model profiles.

    The current models.yaml is provider-first:

        openai:
          orchestrator:
            model: ...

    This registry also supports optional future top-level routing:

        defaults:
          provider: openai
          orchestrator: anthropic

    Capabilities are explicit when present in models.yaml. If omitted, a model is
    treated as text/json capable only. This avoids overclaiming media support.
    """
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.default_provider = self._default_provider()
        self.routes = self._routes()

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_MODELS_PATH) -> "ModelRegistry":
        """Load a registry from a YAML config file."""
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
        return cls(config)

    def for_role(self, role: str, provider: str | None = None) -> ModelProfile:
        """Resolve the model profile for a role such as verifier/orchestrator."""
        selected_provider = provider or self.routes.get(role) or self.default_provider
        provider_config = self.config.get(selected_provider)
        if not isinstance(provider_config, dict):
            raise KeyError(f"Unknown model provider: {selected_provider}")

        role_config = provider_config.get(role)
        if not isinstance(role_config, dict):
            raise KeyError(f"Provider {selected_provider!r} has no role {role!r}")

        model = role_config.get("model")
        if not model:
            raise KeyError(f"Provider {selected_provider!r} role {role!r} has no model")

        capabilities = role_config.get("capabilities") or ["text", "json"]
        settings = role_config.get("settings") or {}

        return ModelProfile(
            provider=selected_provider,
            role=role,
            model=str(model),
            task=role_config.get("task"),
            capabilities=frozenset(str(item) for item in capabilities),
            settings=dict(settings),
        )

    def for_layer(self, layer: str, provider: str | None = None) -> ModelProfile:
        """Alias for for_role(), matching pipeline layer terminology."""
        return self.for_role(layer, provider=provider)

    def capable_profiles(
        self,
        capability: str,
        role: str | None = None,
    ) -> list[ModelProfile]:
        """Return configured profiles that explicitly support a capability."""
        profiles: list[ModelProfile] = []
        for provider, provider_config in self.config.items():
            if provider in {"defaults", "routes", "routing"}:
                continue
            if not isinstance(provider_config, dict):
                continue

            for candidate_role, role_config in provider_config.items():
                if role is not None and candidate_role != role:
                    continue
                if not isinstance(role_config, dict):
                    continue

                try:
                    profile = self.for_role(str(candidate_role), provider=str(provider))
                except KeyError:
                    continue
                if profile.supports(capability):
                    profiles.append(profile)

        return profiles

    def require_capability(
        self,
        capability: str,
        role: str | None = None,
    ) -> ModelProfile:
        """Return the first configured model that supports capability."""
        profiles = self.capable_profiles(capability, role=role)
        if not profiles:
            role_hint = f" for role {role!r}" if role else ""
            raise KeyError(f"No model declares capability {capability!r}{role_hint}")
        return profiles[0]

    def _default_provider(self) -> str:
        """Resolve the provider used when a role has no explicit route."""
        env_provider = os.getenv(DEFAULT_PROVIDER_ENV)
        if env_provider:
            return env_provider

        defaults = self.config.get("defaults")
        if isinstance(defaults, dict) and defaults.get("provider"):
            return str(defaults["provider"])

        return "openai"

    def _routes(self) -> dict[str, str]:
        """Read optional role/layer to provider routes from config."""
        routes: dict[str, str] = {}
        for section_name in ("routes", "routing", "defaults"):
            section = self.config.get(section_name)
            if not isinstance(section, dict):
                continue
            for key, value in section.items():
                if key == "provider":
                    continue
                if isinstance(value, str):
                    routes[str(key)] = value
        return routes


def load_model_registry(path: str | Path = DEFAULT_MODELS_PATH) -> ModelRegistry:
    """
    Convenience loader for stages that do not need to manage registry state.

    The registry is cached so hot-path stages do not re-read models.yaml on
    every request. Tests or config reload code can call cache_clear() on this
    function when they intentionally change model configuration at runtime.
    """
    return _load_model_registry(str(Path(path)))


@lru_cache(maxsize=8)
def _load_model_registry(path: str) -> ModelRegistry:
    """Cached implementation behind load_model_registry()."""
    return ModelRegistry.from_file(path)


load_model_registry.cache_clear = _load_model_registry.cache_clear
