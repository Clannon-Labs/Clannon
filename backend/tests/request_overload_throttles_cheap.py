"""
Hermetic resilience test: request-overload throttles cheap.

Proves three layers of overload protection fire BEFORE any paid LLM stage runs:

  1. Per-identity sliding window (InMemorySlidingWindowRateLimiter): a burst from
     one session_id is blocked at intake; no downstream stage executes.

  2. Global burst window: a rapid fan-out across many distinct identities is
     throttled at intake once the global burst capacity is exhausted.

  3. Per-layer token-budget guard (UsageLimits): the orchestrator's configured
     request_limit (ORCHESTRATOR_MAX_TURNS + 1) and output_tokens_limit cap how
     many tokens a single run can spend, bounding compute cost per request.

  4. Railway short-circuit: a blocked Flow has should_stop == True; Flow.then()
     returns the blocked flow unchanged without invoking the downstream callable.
     This is the mechanism that prevents the sanitizer, verifier, and orchestrator
     from running after intake blocks a rate-limited request.

No paid LLM calls anywhere. The module-level rate limiter singletons are reset
between tests (same autouse fixture pattern as tests/intake.py).
"""

import asyncio

import pytest

from foundation import Flow, constants
import settings
from core.intake import intake, rate_limiter
from core.intake.rate_limiter import (
    InMemorySlidingWindowRateLimiter,
    check_request_rate,
)
from core.llm.registry import usage_limits_for_layer


# ---------------------------------------------------------------------------
# Shared fixture: isolate tests from each other's rate limiter state
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Keep each test independent of shared in-process limiter state."""
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _limiter(max_requests: int = 3, window_s: float = 10.0):
    """Return a rate limiter driven by an injectable fake clock."""
    clock_val = [0.0]

    def clock() -> float:
        return clock_val[0]

    limiter = InMemorySlidingWindowRateLimiter(
        max_requests=max_requests, window_s=window_s, clock=clock,
    )
    return limiter, clock_val


def _run_intake(payload: str, session: str) -> Flow:
    # user_id="" models a PRE-AUTH caller: the limiter then keys on the session id
    # (the documented fallback). Authed callers key on user_id so session rotation
    # can't bypass the window — issue #18, pinned in tests/intake.py.
    return asyncio.run(intake.process(Flow.new(payload, session, user_id="")))


# ---------------------------------------------------------------------------
# 1. InMemorySlidingWindowRateLimiter unit tests
#    Injected fake clock makes window boundaries deterministic.
# ---------------------------------------------------------------------------

def test_limiter_allows_up_to_cap_then_denies():
    """Exactly max_requests are allowed; the very next is denied."""
    limiter, _ = _limiter(max_requests=3)

    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is True
    assert limiter.allow("u1") is False   # 4th denied — at cap


def test_limiter_window_expiry_restores_capacity():
    """Requests that fall outside the rolling window no longer count."""
    limiter, clock = _limiter(max_requests=2, window_s=10.0)

    clock[0] = 0.0
    limiter.allow("u2")
    limiter.allow("u2")
    assert limiter.allow("u2") is False   # at cap

    clock[0] = 11.0                       # advance past the 10s window
    assert limiter.allow("u2") is True    # old requests expired; slot restored


def test_limiter_independent_keys_never_interfere():
    """Exhausting one user_id's window leaves all other users unaffected."""
    limiter, _ = _limiter(max_requests=2)

    limiter.allow("flood")
    limiter.allow("flood")
    assert limiter.allow("flood") is False   # flood user blocked

    assert limiter.allow("clean") is True    # unrelated user still allowed


def test_limiter_new_key_rejected_when_capacity_full():
    """
    When max_tracked_keys is reached a brand-new key is refused immediately,
    even if it has sent zero requests. This stops session-ID rotation attacks
    from bypassing the per-identity limit by cycling to a fresh key each time.
    """
    limiter, _ = _limiter(max_requests=100, window_s=60.0)
    limiter.max_tracked_keys = 2  # tiny cap for the test

    limiter.allow("slot_a")
    limiter.allow("slot_b")

    assert limiter.allow("slot_c") is False   # no room for a third key


# ---------------------------------------------------------------------------
# 2. check_request_rate integration
#    Tests the per-identity + global limiters working in combination.
# ---------------------------------------------------------------------------

def test_per_identity_check_runs_before_global_check(monkeypatch):
    """
    check_request_rate evaluates the per-identity limit BEFORE the global limit.
    A session that exceeds its per-identity cap is denied with the 'identity'
    reason — not the 'global' reason — so one noisy caller cannot exhaust global
    capacity before being blocked.

    Uses a tiny per-identity limiter (cap=2) so the identity window fills before
    the global window (cap=10/s in production) could interfere.
    """
    tiny_id = InMemorySlidingWindowRateLimiter(max_requests=2, window_s=60.0)
    monkeypatch.setattr(rate_limiter, "_identity_rate_limiter", tiny_id)

    assert check_request_rate("flood_user").allowed is True
    assert check_request_rate("flood_user").allowed is True

    denied = check_request_rate("flood_user")
    assert not denied.allowed
    assert denied.reason is not None and "identity" in denied.reason.lower()


def test_global_burst_trips_after_per_identity_allows(monkeypatch):
    """
    A multi-identity burst (many distinct users, each under their per-identity cap)
    is throttled at the global window once it fills up.  A tiny global limiter
    makes the test fast without depending on real wall-clock counts.
    """
    tiny_global = InMemorySlidingWindowRateLimiter(max_requests=3, window_s=60.0)
    monkeypatch.setattr(rate_limiter, "_global_rate_limiter", tiny_global)

    for i in range(3):
        r = check_request_rate(f"user_{i}")
        assert r.allowed, f"user_{i} within global cap must be allowed"

    denied = check_request_rate("user_4")   # new identity but global cap full
    assert not denied.allowed
    assert denied.reason is not None and "global" in denied.reason.lower()


def test_empty_identity_string_falls_back_to_anonymous_and_is_limited(monkeypatch):
    """A blank identity string maps to 'anonymous' and is still rate-limited."""
    tiny_id = InMemorySlidingWindowRateLimiter(max_requests=1, window_s=60.0)
    monkeypatch.setattr(rate_limiter, "_identity_rate_limiter", tiny_id)

    assert check_request_rate("").allowed is True
    denied = check_request_rate("")         # second anonymous request — denied
    assert not denied.allowed


# ---------------------------------------------------------------------------
# 3. Intake stage: rate limit blocks the Flow
#    Proves the guard fires at intake, before any subsequent stage.
# ---------------------------------------------------------------------------

def test_intake_blocks_flow_when_per_identity_limit_exceeded():
    """
    Once a session has exhausted its per-identity request window, the next call to
    intake.process returns a blocked Flow with reason 'rate_limited'.  The block
    is set by intake, the cheapest stage, with no sanitizer/verifier/orchestrator
    ever invoked.
    """
    session = "overloaded_session"
    max_r = settings.INTAKE.rate_limit_max_requests

    # exhaust the identity slot directly through the module-level limiter
    for _ in range(max_r):
        rate_limiter._identity_rate_limiter.allow(session)

    out = _run_intake("legitimate request text", session)

    assert out.blocked, "intake must block the flow"
    assert out.reason == "rate_limited", f"unexpected reason: {out.reason}"


def test_intake_blocks_flow_on_global_burst(monkeypatch):
    """Global burst window trips for the (N+1)-th request, regardless of identity."""
    tiny_global = InMemorySlidingWindowRateLimiter(max_requests=2, window_s=60.0)
    monkeypatch.setattr(rate_limiter, "_global_rate_limiter", tiny_global)

    # fill the global window with two different sessions
    _run_intake("req one", "s_alpha")
    _run_intake("req two", "s_beta")

    # third request from a fresh session hits the global wall
    out = _run_intake("req three", "s_gamma")
    assert out.blocked and out.reason == "rate_limited"


def test_intake_block_has_should_stop_set():
    """A rate-limited block marks should_stop so the Railway pipeline stops."""
    session = "should_stop_session"
    for _ in range(settings.INTAKE.rate_limit_max_requests):
        rate_limiter._identity_rate_limiter.allow(session)

    out = _run_intake("hello", session)

    assert out.should_stop, "should_stop must be True so pipeline drive() breaks"


# ---------------------------------------------------------------------------
# 4. Railway short-circuit: blocked flow never reaches downstream stages
#    Uses Flow.then() directly -- the same mechanism pipeline.drive() relies on.
# ---------------------------------------------------------------------------

def test_blocked_flow_never_invokes_downstream_via_then():
    """
    A blocked Flow returned by intake must never execute any downstream callable.
    Flow.then() is the Railway short-circuit that pipeline.drive() relies on;
    testing it here proves the guarantee at the mechanism level.
    """
    session = "short_circuit_session"
    for _ in range(settings.INTAKE.rate_limit_max_requests):
        rate_limiter._identity_rate_limiter.allow(session)

    blocked = _run_intake("payload", session)
    assert blocked.blocked

    # simulate the expensive downstream stages (sanitizer, verifier, orchestrator)
    invoked = []

    async def fake_sanitizer(flow: Flow) -> Flow:
        invoked.append("sanitizer")
        return flow

    async def fake_verifier(flow: Flow) -> Flow:
        invoked.append("verifier")
        return flow

    async def fake_orchestrator(flow: Flow) -> Flow:
        invoked.append("orchestrator")
        return flow

    async def _chain():
        f = await blocked.then(fake_sanitizer)
        f = await f.then(fake_verifier)
        f = await f.then(fake_orchestrator)
        return f

    final = asyncio.run(_chain())

    assert final.blocked, "final flow must still be blocked"
    assert invoked == [], (
        f"rate-limited request must never reach downstream stages; "
        f"got {invoked}"
    )


def test_rate_limited_flow_origin_is_intake():
    """
    The block journal entry originates from INTAKE, proving the expensive stages
    never ran — the block was set at the first (cheapest) gate.
    """
    session = "origin_check_session"
    for _ in range(settings.INTAKE.rate_limit_max_requests):
        rate_limiter._identity_rate_limiter.allow(session)

    out = _run_intake("hello", session)

    from foundation import Origin
    intake_entries = [e for e in out.journal if e.origin == Origin.INTAKE]
    assert intake_entries, "no INTAKE journal entry found on rate-limited flow"
    blocked_entry = intake_entries[-1]
    assert blocked_entry.reason == "rate_limited"


# ---------------------------------------------------------------------------
# 5. Token-budget guard: per-layer UsageLimits cap orchestrator token spend
#    These limits ensure one run cannot spend unbounded tokens even if it
#    is not blocked by the rate limiter.
# ---------------------------------------------------------------------------

def test_orchestrator_request_limit_matches_max_turns_constant():
    """
    usage_limits_for_layer('orchestrator') sets request_limit to
    ORCHESTRATOR_MAX_TURNS + 1 (turns + the mandatory final-answer request).
    This is the cap that fires UsageLimitExceeded if an orchestrator run attempts
    more LLM calls than the configured turn budget allows.
    """
    limits = usage_limits_for_layer("orchestrator")
    expected = constants.ORCHESTRATOR_MAX_TURNS + 1
    assert limits.request_limit == expected, (
        f"expected request_limit={expected}, got {limits.request_limit}"
    )


def test_orchestrator_output_token_cap_is_configured():
    """
    The orchestrator's output_tokens_limit matches ORCHESTRATOR_MAX_TOKENS,
    bounding the number of output tokens any single orchestrator run can generate.
    """
    limits = usage_limits_for_layer("orchestrator")
    assert limits.output_tokens_limit == constants.ORCHESTRATOR_MAX_TOKENS, (
        f"expected output_tokens_limit={constants.ORCHESTRATOR_MAX_TOKENS}, "
        f"got {limits.output_tokens_limit}"
    )


def test_verifier_request_limit_matches_retry_budget():
    """
    Verifier request_limit = VERIFIER_MAX_RETRIES + 1 (same pattern as in
    tests/verifier.py — included here to confirm the budget guard pattern holds
    across all LLM stages, not just the orchestrator).
    """
    limits = usage_limits_for_layer("verifier")
    assert limits.request_limit == settings.VERIFIER.max_retries + 1


def test_per_run_turn_override_applies_correctly():
    """
    When a caller passes max_turns, usage_limits_for_layer switches to that cap
    (max_turns + 1), letting a single run use a narrower per-request budget.
    """
    limits = usage_limits_for_layer("orchestrator", max_turns=5)
    assert limits.request_limit == 6   # 5 turns + final answer request
