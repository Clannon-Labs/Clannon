"""Thin LLM framework adapter surface for core stages."""

from .registry import model_name_for_layer, model_overrides, model_settings_for_layer, usage_limits_for_layer
from .retry import run_agent
from .framework import AgentHandle, RunContext, build_agent, build_tool_agent, run_structured
from .search import SearchResult, grounded_search

__all__ = [
    "model_name_for_layer",
    "model_overrides",
    "model_settings_for_layer",
    "usage_limits_for_layer",
    "run_agent",
    "AgentHandle",
    "RunContext",      # re-exported so capability code uses SDK types via this boundary only
    "build_agent",
    "build_tool_agent",
    "run_structured",
    "SearchResult",
    "grounded_search",
]
