from __future__ import annotations

from dataclasses import dataclass

from src.providers.imports import PROVIDERS_PRIORITY_ORDER


@dataclass(frozen=True)
class ModelCandidate:
    provider_name: str
    model_name: str

    def instantiate(self):
        from src.providers.factory import get_model_instance

        return get_model_instance(self.provider_name, self.model_name)

    def __str__(self):
        model_class = PROVIDERS_PRIORITY_ORDER.get(self.provider_name)
        class_name = model_class.__name__ if model_class else self.provider_name
        return f"{class_name}({self.model_name})"
