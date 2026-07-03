"""Characterization tests for how the orchestrator's graceful-degradation path
(core/orchestrator/utils/recovery.classify_failure) maps representative provider
exceptions to the three user-facing reasons: ``rate_limit`` / ``timeout`` /
``error``.

These pin CURRENT behavior. recovery collapses the shared classifier's richer
kinds down to three: a transient server / transport fault ("server_error") is
surfaced to the user as a generic ``error`` (the user only needs the actionable
reason, not the HTTP shape), and rate-limit wins over timeout.

This is one of TWO independent classification pins. How the retry wrapper treats
the SAME exceptions (transient -> retry, fatal -> re-raise) is pinned separately
in ``llm_retry_classification.py``. The two are deliberately NOT asserted against
each other and DO diverge: every transient 5xx / transport fault below reads as
``error`` here, yet the retry wrapper retries those same exceptions. Each module
keeps its own policy; do not unify them.

Group / FallbackModel-exhaustion shapes and the cyclic-cause guard are
characterized in ``orchestrator_recovery.py``; this file pins the
single-exception table plus the one canonical FallbackModel-exhaustion shape.
"""

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UsageLimitExceeded

from core.orchestrator.utils.recovery import classify_failure


def _http(status_code):
    return ModelHTTPError(status_code=status_code, model_name="google:gemini-2.5-flash", body=None)


# (label, exception, expected_kind). recovery.classify_failure has no side
# effects, so plain instances (not factories) are fine.
_CASES = [
    # Rate limit, by HTTP status, by message text, and the canonical FallbackModel
    # rate-limit storm (a 429 anywhere in the group wins).
    ("http_429",               _http(429), "rate_limit"),
    ("rate_limit_by_message",  RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"), "rate_limit"),
    ("overloaded_by_message",  RuntimeError("the model is overloaded, please retry"), "rate_limit"),
    ("usage_limits_message",   RuntimeError("anthropic: usage limits reached"), "rate_limit"),
    ("fallback_group_with_429",
        ExceptionGroup("All models from FallbackModel failed", [_http(503), _http(429)]),
        "rate_limit"),
    # Wall-clock timeout (asyncio.TimeoutError is the builtin TimeoutError on 3.11+).
    ("plain_timeout",          TimeoutError(), "timeout"),
    # Transient server / transport faults collapse to a generic user-facing error
    # (the retry wrapper still retries these; recovery only shapes what the user hears).
    ("http_500",               _http(500), "error"),
    ("http_503",               _http(503), "error"),
    ("http_408",               _http(408), "error"),
    ("model_api_transport",    ModelAPIError("google:gemini-2.5-flash", "transport connection reset"), "error"),
    # Permanent 4xx -> generic error.
    ("http_400",               _http(400), "error"),
    ("http_401",               _http(401), "error"),
    ("http_404",               _http(404), "error"),
    # Usage / quota cap and any other fault -> generic error.
    ("usage_limit_exceeded",   UsageLimitExceeded("exceeded the request limit"), "error"),
    ("generic_runtime_error",  RuntimeError("null pointer somewhere"), "error"),
]


@pytest.mark.parametrize("label,exc,expected_kind", _CASES, ids=[c[0] for c in _CASES])
def test_recovery_classifies_provider_exception(label, exc, expected_kind):
    assert classify_failure(exc) == expected_kind
