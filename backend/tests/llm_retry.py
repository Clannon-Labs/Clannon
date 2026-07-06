"""Tests for the shared transient-error retry wrapper (core/llm/retry.py)."""

import asyncio

import httpx
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

from core.llm import retry
from core.llm.retry import run_agent


class FakeAgent:
    """Minimal stand-in: its run() replays a scripted sequence of outcomes."""
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def run(self, *args, **kwargs):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _no_sleep(monkeypatch):
    async def fake_sleep(_):
        return None
    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)


def _503():
    return ModelHTTPError(status_code=503, model_name="google:gemini-2.5-flash", body=None)


def test_retries_transient_then_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    agent = FakeAgent([_503(), _503(), "ok"])

    result = asyncio.run(run_agent(agent, "prompt"))

    assert result == "ok"
    assert agent.calls == 3  # two transient failures, third succeeds


def test_exhausts_budget_and_reraises_last_transient(monkeypatch):
    _no_sleep(monkeypatch)
    import settings
    # budget = transient_max_retries + 1 attempts, all 503
    attempts = settings.LLM.transient_max_retries + 1
    agent = FakeAgent([_503() for _ in range(attempts)])

    try:
        asyncio.run(run_agent(agent, "prompt"))
        assert False, "should have raised after exhausting retries"
    except ModelHTTPError as exc:
        assert exc.status_code == 503

    assert agent.calls == attempts  # fails closed after the bounded budget


def test_permanent_http_error_is_not_retried(monkeypatch):
    _no_sleep(monkeypatch)
    bad_request = ModelHTTPError(status_code=400, model_name="m", body=None)
    agent = FakeAgent([bad_request, "ok"])

    try:
        asyncio.run(run_agent(agent, "prompt"))
        assert False, "4xx should raise immediately"
    except ModelHTTPError as exc:
        assert exc.status_code == 400

    assert agent.calls == 1  # no retry on a permanent fault


def test_usage_limit_is_not_retried(monkeypatch):
    _no_sleep(monkeypatch)
    agent = FakeAgent([UsageLimitExceeded("limit"), "ok"])

    try:
        asyncio.run(run_agent(agent, "prompt"))
        assert False, "usage-limit should raise immediately"
    except UsageLimitExceeded:
        pass

    assert agent.calls == 1


def test_connection_timeout_is_transient(monkeypatch):
    _no_sleep(monkeypatch)
    agent = FakeAgent([httpx.ConnectTimeout("timeout"), "ok"])

    result = asyncio.run(run_agent(agent, "prompt"))

    assert result == "ok"
    assert agent.calls == 2


def test_fallback_chain_exhaustion_with_rate_limit_is_retried(monkeypatch):
    _no_sleep(monkeypatch)
    # FallbackModel raises an ExceptionGroup when every chain entry fails; a
    # 429 member means a backoff retry of the whole chain can succeed.
    group = ExceptionGroup("All models failed", [
        ModelHTTPError(status_code=429, model_name="anthropic:claude-haiku-4-5", body=None),
        ModelHTTPError(status_code=401, model_name="openai:gpt-5.4-mini", body=None),
    ])
    agent = FakeAgent([group, "ok"])
    assert asyncio.run(run_agent(agent, "prompt")) == "ok"
    assert agent.calls == 2


def test_fallback_chain_exhaustion_is_capped_not_full_budget(monkeypatch):
    _no_sleep(monkeypatch)
    import settings
    # every attempt exhausts the WHOLE chain (all rate-limited). The wrapper must not
    # spend the full single-model budget re-running the chain (that multiplies latency by
    # the chain length and spins to the expert timeout) — it caps whole-chain re-runs and
    # fails fast into graceful degradation.
    def group():
        return ExceptionGroup("All models failed", [
            ModelHTTPError(status_code=429, model_name="google:gemini-2.5-flash", body=None),
        ])
    agent = FakeAgent([group() for _ in range(settings.LLM.transient_max_retries + 1)])
    try:
        asyncio.run(run_agent(agent, "prompt"))
        assert False, "should raise after the capped chain retries"
    except ExceptionGroup:
        pass
    # first attempt + fallback_max_retries re-runs, NOT the full transient budget
    assert agent.calls == settings.LLM.fallback_max_retries + 1


def test_fallback_chain_exhaustion_all_permanent_not_retried(monkeypatch):
    _no_sleep(monkeypatch)
    group = ExceptionGroup("All models failed", [
        ModelHTTPError(status_code=401, model_name="anthropic:claude-haiku-4-5", body=None),
        ModelHTTPError(status_code=404, model_name="openai:gpt-old", body=None),
    ])
    agent = FakeAgent([group])
    try:
        asyncio.run(run_agent(agent, "prompt"))
        assert False, "should have raised immediately"
    except ExceptionGroup:
        pass
    assert agent.calls == 1  # no retry budget wasted on permanent faults
