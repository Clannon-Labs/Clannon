"""Expert sub-layer. The handler is the orchestrator's single door to experts;
each expert package self-registers with the capability registry on import."""

from .handler import ExpertHandler

__all__ = ["ExpertHandler"]
