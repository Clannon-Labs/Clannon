"""Thin LLM framework adapter surface for core stages."""

from .registry import model_name_for_layer, model_overrides, model_settings_for_layer, usage_limits_for_layer
from .failures import FailureKind, classify_failure, is_transient
from .retry import run_agent
from .usage import Usage, usage_scope
from .framework import AgentHandle, RunContext, Tool, build_agent, build_tool_agent, run_structured
from .search import SearchResult, grounded_search

__all__ = [
    "model_name_for_layer",
    "model_overrides",
    "model_settings_for_layer",
    "usage_limits_for_layer",
    "FailureKind",
    "classify_failure",
    "is_transient",
    "run_agent",
    "Usage",
    "usage_scope",
    "AgentHandle",
    "RunContext",      # re-exported so capability code uses SDK types via this boundary only
    "Tool",            # ditto: lets capability code mark a tool deferred without importing the SDK
    "build_agent",
    "build_tool_agent",
    "run_structured",
    "SearchResult",
    "grounded_search",
]
