"""
Proof suite for the Redis atomic budget broker (`core.budget.redis_budget.RedisBudget`).

This is the money layer, so the tests here are the guarantee — not illustrations. The ones
that matter most and that PHASE_BATCH_REDIS Part A names explicitly:
  * no overspend under concurrency (N racing reserves against a near-empty budget → exactly
    the affordable number pass, the balance never goes negative),
  * all-or-nothing across the two ceilings (a mission-short reserve never touches the user's
    budget),
  * fail-closed (no user_id, or the store unreachable → the call is REFUSED, never let through),
  * idempotent reconcile (a replayed settle never double-refunds).

Backed by `fakeredis.aioredis` — it runs the same Lua `EVAL` path atomically, so the
concurrency proof is real (verified: 10 parallel reserves of 10 against 50 → exactly 5 grant,
balance ends at 0). A real-Redis integration run is a CI follow-up; the enforcement LOGIC and
its fail-closed posture are fully exercised here.

Async tests use the suite's `asyncio.run(go())`-inside-a-plain-`def` convention (matching
`tests/mission_operate.py`), so no pytest-asyncio dependency is needed.
"""
import asyncio

import pytest
from fakeredis import aioredis

from foundation import BudgetExhausted, BudgetReservation, BudgetScope
from core.budget.redis_budget import RedisBudget

_PERIOD = "2026-07"  # fixed so keys are deterministic (real code uses the live calendar month)


def _run(coro):
    return asyncio.run(coro)


def _budget(client) -> RedisBudget:
    return RedisBudget(client, period_provider=lambda: _PERIOD)


async def _seed(client, *, user: int | None = None, mission: tuple[str, int] | None = None):
    if user is not None:
        await client.set(f"budget:user:u1:{_PERIOD}", user)
    if mission is not None:
        mid, amt = mission
        await client.set(f"budget:mission:{mid}", amt)


# ── reserve: grant + decrement ───────────────────────────────────────────────────────────────

def test_reserve_grants_and_decrements_the_user_ceiling():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000)
        b = _budget(r)
        resv = await b.reserve(BudgetScope(user_id="u1"), 300)
        assert isinstance(resv, BudgetReservation) and resv.estimated == 300
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 700  # taken atomically
    _run(go())


def test_reserve_checks_both_ceilings_and_decrements_both():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000, mission=("m1", 400))
        b = _budget(r)
        await b.reserve(BudgetScope(user_id="u1", mission_id="m1"), 250)
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 750
        assert int(await r.get("budget:mission:m1")) == 150
    _run(go())


# ── reserve: denial + all-or-nothing + fail-closed ───────────────────────────────────────────

def test_reserve_denies_when_user_short_without_touching_the_balance():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=100)
        b = _budget(r)
        with pytest.raises(BudgetExhausted) as exc:
            await b.reserve(BudgetScope(user_id="u1"), 500)
        assert exc.value.ceiling == "user"
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 100  # untouched — no partial take
    _run(go())


def test_reserve_mission_short_is_all_or_nothing_user_untouched():
    # The core all-or-nothing guarantee: the user ceiling has plenty, the mission ceiling is
    # short — NEITHER may be decremented, or an autonomous mission could bleed the user's wallet.
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=10_000, mission=("m1", 50))
        b = _budget(r)
        with pytest.raises(BudgetExhausted) as exc:
            await b.reserve(BudgetScope(user_id="u1", mission_id="m1"), 200)
        assert exc.value.ceiling == "mission"
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 10_000  # user NOT touched
        assert int(await r.get("budget:mission:m1")) == 50         # mission NOT touched
    _run(go())


def test_reserve_with_no_user_id_fails_closed():
    async def go():
        r = aioredis.FakeRedis()
        b = _budget(r)
        with pytest.raises(BudgetExhausted):
            await b.reserve(BudgetScope(user_id=""), 1)
    _run(go())


def test_reserve_on_a_missing_budget_fails_closed_not_open():
    # An unknown budget key is treated as "can't afford", never as unlimited.
    async def go():
        r = aioredis.FakeRedis()  # nothing seeded
        b = _budget(r)
        with pytest.raises(BudgetExhausted):
            await b.reserve(BudgetScope(user_id="u1"), 1)
    _run(go())


def test_reserve_rejects_a_negative_estimate_without_inflating_the_balance():
    # Regression (security review, 2026-07-06): a negative estimate must be REFUSED, never turned
    # into a balance-inflating credit — a negative DECRBY is an INCRBY, so the un-guarded path
    # took a balance of 100 up to 1,000,100. The one input a fail-closed money broker must
    # validate at its own boundary no matter how trusted the caller is meant to be.
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=100)
        b = _budget(r)
        with pytest.raises(BudgetExhausted):
            await b.reserve(BudgetScope(user_id="u1"), -1_000_000)
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 100  # untouched, NOT inflated
    _run(go())


def test_budget_scope_rejects_colon_in_ids():
    # ':' is the budget-key delimiter; an id containing it could collide two distinct scopes onto
    # one billing key. Rejected at construction, so every caller (present + future) is covered.
    with pytest.raises(ValueError):
        BudgetScope(user_id="a:b")
    with pytest.raises(ValueError):
        BudgetScope(user_id="u1", mission_id="m:1")


def test_no_mission_reserve_writes_no_sentinel_mission_key():
    # The no-mission path must not leave a 'budget:mission:_none' sentinel a real mission named
    # '_none' could collide with — the KEYS[2] filler is inert (the user key), never a mission key.
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000)
        b = _budget(r)
        await b.reserve(BudgetScope(user_id="u1"), 100)
        assert await r.get("budget:mission:_none") is None
    _run(go())


class _BrokenRedis:
    """A client whose every operation raises — stands in for Redis being unreachable."""
    def register_script(self, _src):
        async def _raise(*a, **k):
            raise ConnectionError("redis down")
        return _raise

    async def get(self, *a, **k):
        raise ConnectionError("redis down")


def test_reserve_when_store_unreachable_refuses_the_call():
    # The one path that must never exist: an un-reserved LLM call proceeding because the store
    # was down. Store unreachable → BudgetExhausted, fast, no hang.
    async def go():
        b = _budget(_BrokenRedis())
        with pytest.raises(BudgetExhausted):
            await b.reserve(BudgetScope(user_id="u1"), 1)
    _run(go())


# ── the headline: no overspend under concurrency ─────────────────────────────────────────────

def test_no_overspend_under_concurrency():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=50)
        b = _budget(r)
        # 10 calls race for 10 µ$ each against 50 µ$ — the SUM (100) far exceeds the budget.
        results = await asyncio.gather(
            *[b.reserve(BudgetScope(user_id="u1"), 10) for _ in range(10)],
            return_exceptions=True,
        )
        granted = [x for x in results if isinstance(x, BudgetReservation)]
        denied = [x for x in results if isinstance(x, BudgetExhausted)]
        assert len(granted) == 5, f"exactly 5 of 10 affordable, got {len(granted)}"
        assert len(denied) == 5
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 0  # never driven negative
    _run(go())


# ── reconcile: refund / charge / idempotent ──────────────────────────────────────────────────

def test_reconcile_refunds_the_over_estimate():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000)
        b = _budget(r)
        resv = await b.reserve(BudgetScope(user_id="u1"), 300)   # balance 700
        await b.reconcile(resv, actual=120)                      # refund 180 → 880
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 880
    _run(go())


def test_reconcile_charges_the_shortfall_when_actual_exceeds_estimate():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000)
        b = _budget(r)
        resv = await b.reserve(BudgetScope(user_id="u1"), 300)   # balance 700
        await b.reconcile(resv, actual=500)                      # charge extra 200 → 500
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 500
    _run(go())


def test_reconcile_is_idempotent_a_replay_does_not_double_settle():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000)
        b = _budget(r)
        resv = await b.reserve(BudgetScope(user_id="u1"), 300)   # 700
        await b.reconcile(resv, actual=100)                      # refund 200 → 900
        await b.reconcile(resv, actual=100)                      # replay → no-op
        await b.reconcile(resv, actual=100)                      # replay → no-op
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 900
    _run(go())


def test_reconcile_settles_both_ceilings():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=1000, mission=("m1", 400))
        b = _budget(r)
        resv = await b.reserve(BudgetScope(user_id="u1", mission_id="m1"), 250)  # u750 m150
        await b.reconcile(resv, actual=100)                                       # +150 each
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 900
        assert int(await r.get("budget:mission:m1")) == 300
    _run(go())


def test_reconcile_never_raises_onto_the_caller_even_if_store_down():
    async def go():
        b = _budget(_BrokenRedis())
        resv = BudgetReservation(reservation_id="x", scope=BudgetScope(user_id="u1"), estimated=1)
        await b.reconcile(resv, actual=1)  # must simply return, not raise
    _run(go())


# ── remaining: snapshot + fail-closed to empty ───────────────────────────────────────────────

def test_remaining_snapshots_both_ceilings():
    async def go():
        r = aioredis.FakeRedis()
        await _seed(r, user=800, mission=("m1", 200))
        b = _budget(r)
        snap = await b.remaining(BudgetScope(user_id="u1", mission_id="m1"))
        assert snap.user_remaining == 800 and snap.mission_remaining == 200
        assert snap.period == _PERIOD
    _run(go())


def test_remaining_fails_closed_to_empty_on_store_fault():
    # A store fault must read as EMPTY (pauses work), never as unlimited (waves it through).
    async def go():
        b = _budget(_BrokenRedis())
        snap = await b.remaining(BudgetScope(user_id="u1"))
        assert snap.user_remaining == 0
    _run(go())
