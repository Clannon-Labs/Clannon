"""
Grounded web search via the provider's built-in search (Gemini grounding).

Kept inside core/llm so the provider SDK stays confined to this package. Returns
text findings (with source URLs requested in-prompt) for the web_search tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
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


@lru_cache(maxsize=None)
def _search_agent(layer: str) -> Agent:
    """The grounded-search agent for a layer, built ONCE and reused (W7).

    pydantic-ai model objects are stateless and reusable, so rebuilding a fresh Agent
    (and its provider/HTTP client) on every search was pure waste. Cached per layer;
    the underlying `model_for_layer` keeps its own quota-resilience fallback chain
    (one entry per Google API key) so account-level quota exhaustion still rotates."""
    settings = model_settings_for_layer(layer)
    model = model_for_layer(layer)
    try:
        return Agent(model, builtin_tools=_web_search_builtins(),
                     model_settings=settings, defer_model_check=True)
    except TypeError:
        # Older SDK without builtin_tools: still return model text (no grounding).
        return Agent(model, model_settings=settings, defer_model_check=True)


# A URL as it appears in grounded prose / grounding metadata; trailing sentence
# punctuation is stripped by the caller so "(see https://x.com/a)." yields a clean URL.
_URL_RE = re.compile(r"https?://[^\s)\]}<>\"']+")


def _extract_sources(result: Any, findings: str) -> list[str]:
    """Best-effort, provider-agnostic grounding URLs (closes the old `sources=[]` TODO).

    Pulls URLs from (1) any URL-bearing parts the provider's grounding surfaced on the
    result messages and (2) the grounded findings text itself, which is asked to cite its
    sources inline. De-duplicated, order-preserved, trailing punctuation trimmed. Anything
    unparseable is skipped — a search never fails over source extraction."""
    raw: list[str] = []
    try:
        for msg in result.all_messages():
            for part in getattr(msg, "parts", ()):  # native-tool returns may carry grounding text
                content = getattr(part, "content", None)
                if isinstance(content, str):
                    raw += _URL_RE.findall(content)
    except Exception:  # noqa: BLE001 — message shape varies by provider; the text scan below still runs
        pass
    raw += _URL_RE.findall(findings or "")
    seen: set[str] = set()
    out: list[str] = []
    for url in raw:
        url = url.rstrip(".,;:'\")")
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


async def grounded_search(query: str, *, layer: str = "search") -> SearchResult:
    """Run a grounded search and return findings text + the source URLs it grounded on.

    The findings are kept SOURCE-ATTRIBUTED rather than paraphrased into a lossy summary:
    the research expert that calls this does the final synthesis, so this layer should
    preserve specifics + citations, not pre-summarize them away (W7)."""
    agent = _search_agent(layer)
    prompt = (
        "Search the web for the query below and report what you find. Preserve concrete "
        "specifics (names, numbers, dates, quotes) and keep each key claim attached to the "
        "source URL it came from, as an inline citation. Do not over-summarize or drop "
        "details: a downstream step does the final synthesis, so your job is faithful, "
        "well-sourced findings, not a polished paragraph.\n\nQuery: " + query
    )
    result = await run_agent(agent, prompt)
    text = result.output if isinstance(result.output, str) else str(result.output)
    return SearchResult(findings=text, sources=_extract_sources(result, text))
