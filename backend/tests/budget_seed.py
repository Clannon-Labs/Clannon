"""
Proof suite for budget seeding + the margin-ceiling formula (`core.budget.seed`).

The ceiling formula is the money-correctness core, so its single-source is locked here (invariant
A1): `ceiling_micros` must derive from exactly `settings.BUDGET.spend_ceiling_fraction`. The
seeding primitives are proven SETNX-safe (a re-seed never wipes a live period's spend) and shown
to compose with the RedisBudget broker end-to-end (seed → reserve spends against it).

Async tests use the suite's `asyncio.run(go())`-in-a-plain-`def` convention.
"""
import asyncio
from math import floor

import pytest
from fakeredis import aioredis

import settings
from foundation import BudgetExhausted, BudgetScope
from core.budget.seed import ceiling_micros, seed_mission_cap, seed_user_period
from core.budget.redis_budget import RedisBudget

_PERIOD = "2026-07"


def _run(coro):
    return asyncio.run(coro)


# ── the margin ceiling — SINGLE SOURCE (A1) ──────────────────────────────────────────────────

def test_ceiling_micros_derives_from_the_one_config_key():
    frac = settings.BUDGET.spend_ceiling_fraction
    for paid in (0, 1, 1_000_000, 12_345_678, 999_999_999):
        assert ceiling_micros(paid) == floor(frac * paid)
    # concrete lock at the shipped default (0.80): a user may spend ≤ 80% of what they paid.
    assert settings.BUDGET.spend_ceiling_fraction == 0.80
    assert ceiling_micros(1_000_000) == 800_000


def test_ceiling_micros_clamps_negative_paid_to_zero():
    # A negative amount-paid is a caller bug, never a negative or unbounded budget.
    assert ceiling_micros(-5_000) == 0


# ── seeding — SETNX-safe (a re-seed never wipes a live period) ────────────────────────────────

def test_seed_user_period_writes_the_budget():
    async def go():
        r = aioredis.FakeRedis()
        wrote = await seed_user_period(r, "u1", _PERIOD, 800_000)
        assert wrote is True
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 800_000
    _run(go())


def test_reseed_of_a_live_period_does_not_wipe_spent_balance():
    # The critical safety property: mid-period, the balance reflects spend. A stray re-seed
    # (SETNX) must NOT reset it back to full — that would hand the user their budget again.
    async def go():
        r = aioredis.FakeRedis()
        await seed_user_period(r, "u1", _PERIOD, 800_000)
        await r.set(f"budget:user:u1:{_PERIOD}", 300_000)          # simulate 500k spent
        wrote = await seed_user_period(r, "u1", _PERIOD, 800_000)  # stray re-seed
        assert wrote is False
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 300_000  # untouched
    _run(go())


def test_seed_overwrite_true_resets_the_current_period():
    async def go():
        r = aioredis.FakeRedis()
        await seed_user_period(r, "u1", _PERIOD, 800_000)
        await r.set(f"budget:user:u1:{_PERIOD}", 10)
        wrote = await seed_user_period(r, "u1", _PERIOD, 800_000, overwrite=True)
        assert wrote is True
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 800_000
    _run(go())


def test_seed_clamps_negative_budget_and_rejects_empty_ids():
    async def go():
        r = aioredis.FakeRedis()
        await seed_user_period(r, "u1", _PERIOD, -100)
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 0     # negative → 0, never fail-open
        assert await seed_user_period(r, "", _PERIOD, 100) is False
        assert await seed_user_period(r, "u1", "", 100) is False
    _run(go())


def test_seed_mission_cap_is_setnx_and_write_once():
    async def go():
        r = aioredis.FakeRedis()
        assert await seed_mission_cap(r, "m1", 50_000) is True
        assert await seed_mission_cap(r, "m1", 999_999) is False  # can't silently raise the cap
        assert int(await r.get("budget:mission:m1")) == 50_000
        assert await seed_mission_cap(r, "", 1) is False
    _run(go())


# ── seed + broker compose end-to-end ─────────────────────────────────────────────────────────

def test_seeded_budget_is_spendable_through_the_broker():
    async def go():
        r = aioredis.FakeRedis()
        # A user who paid $1 (1_000_000 µ$) gets an 800_000 µ$ ceiling.
        await seed_user_period(r, "u1", _PERIOD, ceiling_micros(1_000_000))
        b = RedisBudget(r, period_provider=lambda: _PERIOD)
        resv = await b.reserve(BudgetScope(user_id="u1"), 300_000)
        assert resv.estimated == 300_000
        assert int(await r.get(f"budget:user:u1:{_PERIOD}")) == 500_000
        # spending past the seeded ceiling is refused (fail-closed)
        with pytest.raises(BudgetExhausted):
            await b.reserve(BudgetScope(user_id="u1"), 600_000)
    _run(go())


def test_an_unseeded_user_cannot_spend():
    # No seed = no budget = fail-closed (never treated as unlimited).
    async def go():
        r = aioredis.FakeRedis()
        b = RedisBudget(r, period_provider=lambda: _PERIOD)
        with pytest.raises(BudgetExhausted):
            await b.reserve(BudgetScope(user_id="u1"), 1)
    _run(go())


# ── security review 2026-07-25 regressions ───────────────────────────────────────────────────

def test_user_and_mission_namespaces_are_disjoint():
    # Finding 1: a user whose id is literally "mission" must NOT collide with mission-cap keys and
    # silently starve a mission's safety cap (SETNX returns False without raising).
    async def go():
        r = aioredis.FakeRedis()
        await seed_user_period(r, "mission", "m2", 12)        # ordinary-looking user-period seed
        wrote = await seed_mission_cap(r, "m2", 50_000)       # the REAL mission cap
        assert wrote is True                                  # the cap lands, not starved
        assert int(await r.get("budget:mission:m2")) == 50_000
        assert int(await r.get("budget:user:mission:m2")) == 12   # the user seed is a separate key
    _run(go())


def test_seed_rejects_colon_in_ids_and_period():
    # Finding 2: `:` is the key delimiter — reject it on the write side, same as BudgetScope does
    # on the read side, so a "victim:2026-07" id can't inject/collide a key.
    async def go():
        r = aioredis.FakeRedis()
        with pytest.raises(ValueError):
            await seed_user_period(r, "victim:2026-07", "evil", 777)
        with pytest.raises(ValueError):
            await seed_user_period(r, "u1", "2026:07", 100)
        with pytest.raises(ValueError):
            await seed_mission_cap(r, "m:1", 100)
    _run(go())
