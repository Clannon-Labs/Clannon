"""Public provider API for model selection and construction.

Import from this package when code needs provider priorities, model creation, or
provider metadata. Implementation details stay split across the focused modules
beside this file.
"""

from .candidate import ModelCandidate
from .defaults import DEFAULT_MODELS
from .env import PYDANTIC_AI_ENV_MAPPING
from .factory import get_model_instance
from .imports import PROVIDERS_PRIORITY_ORDER
from .priorities import get_model_priorities

__all__ = [
    "DEFAULT_MODELS",
    "ModelCandidate",
    "PROVIDERS_PRIORITY_ORDER",
    "PYDANTIC_AI_ENV_MAPPING",
    "get_model_instance",
    "get_model_priorities",
]
