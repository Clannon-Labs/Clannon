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


# --- budget anchor: mission_id is read LIVE from deps.ctx at each call, never a stale
# ContextVar mirror (docs/architecture/BUDGET_ENFORCEMENT_ANCHOR.md resolution #2) --------

def _enforcement_on(monkeypatch):
    """`settings.BUDGET` is frozen — swap in a copy with enforcement on. The model_id/estimate
    resolution in framework.py only runs when this flag is set (security review 2026-07-26,
    finding 1: it must stay OFF-by-default-inert, so these tests opt in explicitly)."""
    import settings
    monkeypatch.setattr(
        settings, "BUDGET",
        settings.BudgetConfig(**{**settings.BUDGET.model_dump(), "enforcement_enabled": True}),
    )


def test_mission_id_is_read_live_from_deps_ctx_and_model_id_resolved(monkeypatch):
    _enforcement_on(monkeypatch)
    import core.llm.framework as framework_mod

    captured = {}

    async def fake_run_agent(agent, *args, **kwargs):
        captured.update(kwargs)
        return _Result("hello")

    monkeypatch.setattr(framework_mod, "run_agent", fake_run_agent)

    class _Ctx:
        mission_id = "mission-42"

    class _Deps:
        ctx = _Ctx()

    handle = AgentHandle(_OkAgent(), "verifier")
    asyncio.run(run_structured(handle, "prompt", deps=_Deps()))

    assert captured["budget_mission_id"] == "mission-42"   # live off deps.ctx, not a ContextVar
    assert captured["budget_model_id"]                     # resolved to a bare (unprefixed) model id
    assert ":" not in captured["budget_model_id"]
    assert captured["budget_estimate_micros"] > 0


def test_estimate_stays_zero_and_unresolved_when_enforcement_is_off(monkeypatch):
    # The OFF-by-default proof: no registry lookup, no pricing lookup, at all.
    import core.llm.framework as framework_mod

    captured = {}

    async def fake_run_agent(agent, *args, **kwargs):
        captured.update(kwargs)
        return _Result("hello")

    monkeypatch.setattr(framework_mod, "run_agent", fake_run_agent)

    handle = AgentHandle(_OkAgent(), "verifier")
    asyncio.run(run_structured(handle, "prompt"))

    assert captured["budget_model_id"] == ""
    assert captured["budget_estimate_micros"] == 0


def test_unpriced_model_blocks_rather_than_silently_reserving_zero(monkeypatch):
    # Pins security review 2026-07-26 finding 1: a bare `except Exception: pass` used to
    # swallow cost.py's fail-closed KeyError for an unpriced model into a silent 0 estimate,
    # which trivially passes any reserve() check regardless of remaining balance. Now it must
    # raise BudgetExhausted instead — loud, and it must never reach run_agent at all.
    _enforcement_on(monkeypatch)
    import core.llm.framework as framework_mod
    from foundation import BudgetExhausted

    monkeypatch.setattr(framework_mod, "model_name_for_layer", lambda layer: "totally-unpriced-model-xyz")

    called = {"run_agent": False}

    async def fake_run_agent(agent, *args, **kwargs):
        called["run_agent"] = True
        return _Result("hello")

    monkeypatch.setattr(framework_mod, "run_agent", fake_run_agent)

    handle = AgentHandle(_OkAgent(), "verifier")
    try:
        asyncio.run(run_structured(handle, "prompt"))
        assert False, "an unpriced model must block, never silently run for free"
    except BudgetExhausted:
        pass

    assert called["run_agent"] is False   # blocked before the call ever ran, not billed $0 after


def test_mission_id_defaults_empty_when_deps_has_no_ctx(monkeypatch):
    import core.llm.framework as framework_mod

    captured = {}

    async def fake_run_agent(agent, *args, **kwargs):
        captured.update(kwargs)
        return _Result("hello")

    monkeypatch.setattr(framework_mod, "run_agent", fake_run_agent)

    handle = AgentHandle(_OkAgent(), "verifier")
    asyncio.run(run_structured(handle, "prompt"))  # no deps at all (verifier/filter path)

    assert captured["budget_mission_id"] == ""
