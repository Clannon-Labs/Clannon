"""
Grounded web search via the provider's built-in search (Gemini grounding).

Kept inside core/llm so the provider SDK stays confined to this package. Returns
text findings (with source URLs requested in-prompt) for the web_search tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent

from .registry import model_for_layer, model_settings_for_layer
from .retry import run_agent


@dataclass
class SearchResult:
    findings: str
    sources: list[str] = field(default_factory=list)


def _web_search_builtins() -> list[Any]:
    """Best-effort: the provider's built-in web-search tool, if this SDK exposes it."""
    try:
        from pydantic_ai.builtin_tools import WebSearchTool
        return [WebSearchTool()]
    except Exception:
        return []


def _build_search_agent(layer: str) -> Agent:
    settings = model_settings_for_layer(layer)
    # full quota-resilience: the layer's fallback chain, with one entry per
    # Google API key — account-level quota exhaustion rotates, never fails
    model = model_for_layer(layer)
    try:
        return Agent(model, builtin_tools=_web_search_builtins(),
                     model_settings=settings, defer_model_check=True)
    except TypeError:
        # Older SDK without builtin_tools: still return model text (no grounding).
        return Agent(model, model_settings=settings, defer_model_check=True)


async def grounded_search(query: str, *, layer: str = "search") -> SearchResult:
    """Run a grounded search and return findings text + any source URLs."""
    agent = _build_search_agent(layer)
    prompt = (
        "Search the web and report the key findings for the query below. "
        "Include the source URLs you used.\n\nQuery: " + query
    )
    result = await run_agent(agent, prompt)
    text = result.output if isinstance(result.output, str) else str(result.output)
    # TODO: extract grounding source URLs from provider metadata when reliable;
    # for now the findings text itself carries the URLs.
    return SearchResult(findings=text, sources=[])
