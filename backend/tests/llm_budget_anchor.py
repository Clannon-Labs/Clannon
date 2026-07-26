"""
Tests for the budget-enforcement anchor in `core/llm/retry.py`
(`docs/architecture/BUDGET_ENFORCEMENT_ANCHOR.md`).

Two things must hold, proven separately:
  * OFF (the shipped default) is a true no-op — byte-for-byte the pre-anchor behavior,
    even when a caller passes budget kwargs and a user scope is active.
  * ON (a fake broker, monkeypatched in) reserves once before the call and reconciles once
    after; refunds in FULL on any non-success exit; and treats "enforced but unscoped"
    (a wiring bug) differently from an explicit exempt opt-out.
"""
import asyncio
import logging

import pytest

from foundation import BudgetExhausted, BudgetReservation
from core.llm import retry
from core.llm.retry import run_agent
from core.budget.context import budget_exempt_scope, budget_user_scope


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


class _Usage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.requests = 1


class _Result:
    def __init__(self, input_tokens=10, output_tokens=5):
        self.usage = _Usage(input_tokens, output_tokens)


class FakeBroker:
    """Records every reserve/reconcile call; grants unless told to refuse.

    `reconcile` returns `bool` (True = settled), matching the real `RedisBudget`'s contract:
    it never raises, it signals a swallowed store fault via the return value instead
    (security review 2026-07-26, finding 2). `reconcile_ok` lets a test simulate that fault."""
    def __init__(self, *, grant: bool = True, reconcile_ok: bool = True):
        self.grant = grant
        self.reconcile_ok = reconcile_ok
        self.reserved: list = []
        self.reconciled: list = []

    async def reserve(self, scope, estimate):
        self.reserved.append((scope, estimate))
        if not self.grant:
            raise BudgetExhausted("user billing ceiling reached", ceiling="user")
        return BudgetReservation(reservation_id="resv-1", scope=scope, estimated=estimate)

    async def reconcile(self, reservation, actual):
        self.reconciled.append((reservation, actual))
        return self.reconcile_ok

    async def remaining(self, scope):
        raise NotImplementedError


def _no_sleep(monkeypatch):
    async def fake_sleep(_):
        return None
    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)


# ── OFF (default): a true no-op, even with a scope active and budget kwargs passed ─────────

def test_off_by_default_ignores_budget_kwargs_entirely():
    import settings
    assert settings.BUDGET.enforcement_enabled is False  # the shipped default

    agent = FakeAgent([_Result()])
    with budget_user_scope("u1"):
        result = asyncio.run(run_agent(
            agent, "prompt",
            budget_model_id="claude-sonnet-5", budget_mission_id="",
            budget_estimate_micros=999,
        ))
    assert isinstance(result, _Result)
    assert agent.calls == 1  # unaffected: no broker exists while enforcement is off


# ── ON (fake broker monkeypatched into retry.budget_context.get_broker) ─────────────────────

def test_reserve_once_and_reconcile_once_on_success(monkeypatch):
    broker = FakeBroker()
    monkeypatch.setattr(retry.budget_context, "get_broker", lambda: broker)
    agent = FakeAgent([_Result(input_tokens=100, output_tokens=50)])

    with budget_user_scope("u1"):
        result = asyncio.run(run_agent(
            agent, "prompt",
            budget_model_id="claude-sonnet-5", budget_mission_id="m1",
            budget_estimate_micros=500,
        ))

    assert isinstance(result, _Result)
    assert len(broker.reserved) == 1
    scope, estimate = broker.reserved[0]
    assert scope.user_id == "u1" and scope.mission_id == "m1" and estimate == 500
    assert len(broker.reconciled) == 1
    reservation, actual = broker.reconciled[0]
    assert reservation.reservation_id == "resv-1"
    assert actual > 0  # priced against real input/output tokens, never free


def test_refunds_in_full_when_the_call_ultimately_fails(monkeypatch):
    _no_sleep(monkeypatch)
    broker = FakeBroker()
    monkeypatch.setattr(retry.budget_context, "get_broker", lambda: broker)
    from pydantic_ai.exceptions import ModelHTTPError
    agent = FakeAgent([ModelHTTPError(status_code=400, model_name="m", body=None)])

    with budget_user_scope("u1"):
        with pytest.raises(ModelHTTPError):
            asyncio.run(run_agent(
                agent, "prompt",
                budget_model_id="claude-sonnet-5", budget_mission_id="",
                budget_estimate_micros=500,
            ))

    assert len(broker.reconciled) == 1
    _reservation, actual = broker.reconciled[0]
    assert actual == 0  # full refund, never a partial or missed settle


def test_reconcile_failure_is_logged_distinctly_and_retried_once(monkeypatch, caplog):
    # Pins security review 2026-07-26 finding 2: RedisBudget.reconcile() never raises (its own
    # contract), so retry.py must read the bool return instead of assuming success. A False
    # must (a) NOT set settled, so the finally block makes one more attempt, and (b) log a
    # distinguishable message — not the broker's own single swallowed-fault log line.
    broker = FakeBroker(reconcile_ok=False)
    monkeypatch.setattr(retry.budget_context, "get_broker", lambda: broker)
    agent = FakeAgent([_Result(input_tokens=100, output_tokens=50)])

    with caplog.at_level(logging.ERROR, logger=retry.log.name):
        with budget_user_scope("u1"):
            result = asyncio.run(run_agent(
                agent, "prompt",
                budget_model_id="claude-sonnet-5", budget_mission_id="",
                budget_estimate_micros=500,
            ))

    assert isinstance(result, _Result)             # the real call still succeeded and returned
    assert len(broker.reconciled) == 2             # the success-path attempt + the finally retry
    assert any("no working recovery path" in rec.message for rec in caplog.records)
    assert any("ALSO failed" in rec.message for rec in caplog.records)


def test_reserve_denial_propagates_as_budget_exhausted(monkeypatch):
    broker = FakeBroker(grant=False)
    monkeypatch.setattr(retry.budget_context, "get_broker", lambda: broker)
    agent = FakeAgent([_Result()])

    with budget_user_scope("u1"):
        with pytest.raises(BudgetExhausted):
            asyncio.run(run_agent(
                agent, "prompt",
                budget_model_id="claude-sonnet-5", budget_mission_id="",
                budget_estimate_micros=500,
            ))

    assert agent.calls == 0            # refused before the call ever ran
    assert broker.reconciled == []     # nothing to reconcile — no reservation was granted


def test_enforced_but_unscoped_logs_error_and_runs_unbilled(monkeypatch, caplog):
    broker = FakeBroker()
    monkeypatch.setattr(retry.budget_context, "get_broker", lambda: broker)
    agent = FakeAgent([_Result()])

    with caplog.at_level(logging.ERROR, logger=retry.log.name):
        result = asyncio.run(run_agent(  # no budget_user_scope active — a genuine wiring gap
            agent, "prompt",
            budget_model_id="claude-sonnet-5", budget_mission_id="",
            budget_estimate_micros=500,
        ))

    assert isinstance(result, _Result)   # the call still runs — a metering gap never blocks it
    assert broker.reserved == []         # never reserved: unbilled, exactly what the ERROR warns
    assert any("wiring bug" in rec.message for rec in caplog.records)


def test_exempt_call_skips_quietly_without_logging(monkeypatch, caplog):
    broker = FakeBroker()
    monkeypatch.setattr(retry.budget_context, "get_broker", lambda: broker)
    agent = FakeAgent([_Result()])

    with caplog.at_level(logging.ERROR, logger=retry.log.name):
        with budget_exempt_scope():   # explicit opt-out, distinct from "absence of scope"
            result = asyncio.run(run_agent(
                agent, "prompt",
                budget_model_id="claude-sonnet-5", budget_mission_id="",
                budget_estimate_micros=500,
            ))

    assert isinstance(result, _Result)
    assert broker.reserved == []
    assert caplog.records == []   # an intentional opt-out must never spam an ops-facing ERROR
