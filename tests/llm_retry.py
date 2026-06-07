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
    # default budget = LLM_TRANSIENT_MAX_RETRIES (2) + 1 = 3 attempts, all 503
    agent = FakeAgent([_503(), _503(), _503()])

    try:
        asyncio.run(run_agent(agent, "prompt"))
        assert False, "should have raised after exhausting retries"
    except ModelHTTPError as exc:
        assert exc.status_code == 503

    assert agent.calls == 3  # fails closed after the bounded budget


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
