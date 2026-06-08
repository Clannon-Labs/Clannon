"""Tool sub-layer. The handler is the orchestrator's single door to tools; the
individual tool modules self-register with the capability registry on import."""

from .handler import ToolHandler

__all__ = ["ToolHandler"]
