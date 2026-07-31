"""Characterization tests for how the retry wrapper (core/llm/retry.py) classifies
representative provider exceptions as transient (worth a backoff retry) vs fatal
(re-raise immediately).

These pin CURRENT behavior, observed through the only surface that matters here:
whether ``run_agent`` retries an exception or re-raises it on the first attempt.
A transient exception followed by a success is retried (two ``run`` calls,
returns the success); a fatal exception is re-raised on the first call (one
``run`` call). The classification itself lives in core/llm/failures.is_transient.

This is one of TWO independent classification pins. The orchestrator's
graceful-degradation path is pinned separately in
``orchestrator_recovery_classification.py``. The two are deliberately NOT
asserted against each other: they answer different questions (retry: "retry or
not?"; recovery: "what does the user hear?") and diverge on real cases — every
transient 5xx / transport fault below is retried here but surfaces as a generic
"error" to the user there. Keep them separate.

Group / FallbackModel-exhaustion shapes and the whole-chain retry cap are
characterized in ``llm_retry.py``; this file pins the single-exception table.
"""

import asyncio

import httpx
import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UsageLimitExceeded

from core.llm import retry
from core.llm.failures import classify_failure, is_transient
from core.llm.retry import run_agent


class _FakeAgent:
    """Minimal stand-in whose run() replays a scripted sequence of outcomes."""

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


def _http(status_code):
    return ModelHTTPError(status_code=status_code, model_name="google:gemini-2.5-flash", body=None)


# (label, factory, expected_transient). expected_transient=True means "retried";
# False means "re-raised on the first attempt". Each factory builds a FRESH
# exception so a row can be raised without reusing a consumed instance.
_CASES = [
    # Rate limit and transient server / gateway codes -> retried.
    ("http_429_rate_limit",   lambda: _http(429), True),
    ("http_500_server_error", lambda: _http(500), True),
    ("http_502_bad_gateway",  lambda: _http(502), True),
    ("http_503_unavailable",  lambda: _http(503), True),
    ("http_504_gw_timeout",   lambda: _http(504), True),
    ("http_408_req_timeout",  lambda: _http(408), True),
    # Permanent 4xx (bad request / auth / forbidden / missing model) -> NOT retried.
    ("http_400_bad_request",  lambda: _http(400), False),
    ("http_401_auth",         lambda: _http(401), False),
    ("http_403_forbidden",    lambda: _http(403), False),
    ("http_404_no_model",     lambda: _http(404), False),
    # Transport / connection faults (no HTTP status) -> retried.
    ("httpx_connect_timeout", lambda: httpx.ConnectTimeout("connect timed out"), True),
    ("httpx_read_timeout",    lambda: httpx.ReadTimeout("read timed out"), True),
    ("httpx_connect_error",   lambda: httpx.ConnectError("connection refused"), True),
    ("model_api_transport",   lambda: ModelAPIError("google:gemini-2.5-flash", "transport connection reset"), True),
    # asyncio/builtin TimeoutError (3.11+ alias) -> retried.
    ("asyncio_timeout",       lambda: TimeoutError(), True),
    # Usage / quota cap is a hard fault for the retry budget -> NOT retried.
    ("usage_limit_exceeded",  lambda: UsageLimitExceeded("exceeded the request limit"), False),
    # Anything else (a bug, a plain RuntimeError) -> NOT retried.
    ("generic_runtime_error", lambda: RuntimeError("null pointer somewhere"), False),
    # Rate-limit recognized purely from message text (provider phrasings) -> retried.
    ("rate_limit_by_message", lambda: RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"), True),
    ("overloaded_by_message", lambda: RuntimeError("the model is overloaded, please retry"), True),
]


def test_our_limit_breach_is_never_transient_whatever_its_message_says():
    """A limit breach is OURS, and is decided by TYPE, never by message text.

    pydantic-ai 2.18 appended a help hint to UsageLimitExceeded's message --
    "...see the docs on usage limits... https://ai.pydantic.dev/agent/#usage-limits"
    -- and `usage limits` is one of the provider rate-limit markers. That silently
    reclassified a hit spend/turn ceiling as a transient rate limit, which the retry
    wrapper then RETRIES: spending past the very ceiling the limit enforces. No API
    changed and nothing threw; a documentation link moved.

    So this pins the invariant against the worst case the text could ever contain,
    not against today's wording. If someone reorders classify_failure to consult
    text before type, this goes red.
    """
    hostile = UsageLimitExceeded(
        "429 rate limit: quota exceeded, too many requests -- see the docs on usage limits"
    )
    assert classify_failure(hostile) == "error"
    assert is_transient(hostile) is False


@pytest.mark.parametrize("label,factory,expected_transient", _CASES, ids=[c[0] for c in _CASES])
def test_retry_classifies_provider_exception(monkeypatch, label, factory, expected_transient):
    _no_sleep(monkeypatch)
    exc = factory()
    agent = _FakeAgent([exc, "ok"])

    if expected_transient:
        # transient: the wrapper backs off and re-runs, reaching the success.
        assert asyncio.run(run_agent(agent, "prompt")) == "ok"
        assert agent.calls == 2
    else:
        # fatal: the wrapper re-raises the original exception on the first attempt.
        with pytest.raises(BaseException) as excinfo:
            asyncio.run(run_agent(agent, "prompt"))
        assert excinfo.value is exc
        assert agent.calls == 1
