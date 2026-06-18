"""Tests for the single LLM framework boundary (core/llm/framework.py)."""

import asyncio

from foundation import ConfigError, ModelUnavailableError
from core.llm.framework import AgentHandle, run_structured


class _Result:
    def __init__(self, output):
        self.output = output


class _OkAgent:
    async def run(self, *args, **kwargs):
        return _Result("hello")


class _ProviderBoom:
    async def run(self, *args, **kwargs):
        raise RuntimeError("provider exploded")


class _ConfigBoom:
    async def run(self, *args, **kwargs):
        raise ConfigError("bad config")


def test_run_structured_returns_validated_output():
    handle = AgentHandle(_OkAgent(), "verifier")
    assert asyncio.run(run_structured(handle, "prompt")) == "hello"


def test_provider_error_becomes_model_unavailable():
    handle = AgentHandle(_ProviderBoom(), "verifier")
    try:
        asyncio.run(run_structured(handle, "prompt"))
        assert False, "should have raised"
    except ModelUnavailableError as exc:
        assert "verifier" in str(exc)


def test_foundation_error_propagates_unchanged():
    handle = AgentHandle(_ConfigBoom(), "verifier")
    try:
        asyncio.run(run_structured(handle, "prompt"))
        assert False, "config fault must not be masked as a model outage"
    except ConfigError:
        pass


# --- W3 prompt caching: the stable prefix (system prompt + tool catalog) is
# marked cacheable on every layer, so a multi-turn run pays the prefix once ----

def test_layer_settings_mark_the_cacheable_prefix():
    from core.llm.registry import model_settings_for_layer

    # a tool-driving layer (big system prompt + full tool catalog) and a one-shot
    # security gate both get the cache breakpoints — system instructions always,
    # tool definitions where tools exist (a no-op when there are none).
    for layer in ("orchestrator", "filter"):
        settings = model_settings_for_layer(layer)
        assert settings.get("anthropic_cache_instructions") is True, layer
        assert settings.get("anthropic_cache_tool_definitions") is True, layer


# --- W7: grounded-search agent built once per layer; source URLs extracted ------

def test_search_agent_is_cached_per_layer():
    from core.llm.search import _search_agent
    assert _search_agent("search") is _search_agent("search")   # built once, reused (no fresh Agent per call)


def test_search_extracts_source_urls():
    from core.llm.search import _extract_sources

    class _NoMessages:
        def all_messages(self):
            return []

    findings = "Market grew, per https://example.com/report, and also https://foo.org/data."
    out = _extract_sources(_NoMessages(), findings)
    assert out == ["https://example.com/report", "https://foo.org/data"]   # deduped, trimmed, ordered


# --- W8: message-history caching is on for multi-turn layers, off for one-shots --

def test_message_history_caching_scoped_to_multi_turn_layers():
    from core.llm.registry import model_settings_for_layer
    assert model_settings_for_layer("orchestrator").get("anthropic_cache") is True   # reuses history across turns
    assert model_settings_for_layer("filter").get("anthropic_cache") is None         # one-shot, nothing to reuse
