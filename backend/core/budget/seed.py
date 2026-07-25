"""
Budget seeding + reset — how a period's / mission's budget gets WRITTEN. The RedisBudget broker
only ever SPENDS against a budget that already exists (its own docstring defers seeding); this is
the other half.

The margin ceiling formula lives here, SINGLE-SOURCE (invariant A1): the most a user may spend is
`floor(spend_ceiling_fraction × amount_paid)` in integer µ$, read from exactly ONE config key —
`settings.BUDGET.spend_ceiling_fraction`. Nothing else derives or hardcodes the fraction, so
moving that one key moves every enforced ceiling.

The RESET TRIGGER is deliberately behind a plain-function seam (invariant A4): billing is deferred
(no Stripe webhook wired), so a period reset is just `seed_user_period(...)` called by whatever
real billing event lands later — this module hardcodes NO webhook and the enforcement path never
imports billing. Keying budget by `{user_id}:{period}` (via `redis_budget._user_key`) means a
reset is writing a NEW period key, never mutating a live one; and seeding is SETNX by default so a
stray re-seed of the SAME period can't wipe a user's mid-period spend.
"""
from __future__ import annotations

from math import floor

import settings
from core.budget.redis_budget import _mission_key, _user_key


def _reject_colon(value: str, field: str) -> None:
    """`:` is the budget-key delimiter, so an id/period containing it could inject or collide two
    keys — the SAME hygiene `BudgetScope.__post_init__` enforces on the read/spend side. Enforce it
    here on the write side too (security review 2026-07-25, finding 2): loud, never silent."""
    if ":" in value:
        raise ValueError(f"budget seed {field}={value!r} must not contain ':' (the key delimiter)")


def ceiling_micros(amount_paid_micros: int) -> int:
    """The margin invariant (A1): the ceiling a user may spend, in integer µ$ — the ONE place it
    is computed, sourced from exactly `settings.BUDGET.spend_ceiling_fraction`. A negative
    amount_paid is a caller bug, clamped to 0 (never a negative or unbounded budget)."""
    paid = max(0, amount_paid_micros)
    return floor(settings.BUDGET.spend_ceiling_fraction * paid)


async def seed_user_period(
    redis, user_id: str, period: str, budget_micros: int, *, overwrite: bool = False
) -> bool:
    """Seed (or reset) a user's spendable budget for a billing period. Returns True iff it wrote.

    SETNX by default: seeding is a one-time create per period, so a stray re-seed of a LIVE period
    can't wipe the spend already recorded against it. A genuine billing reset lands on a NEW period
    key (SETNX succeeds because that key does not exist yet). Pass `overwrite=True` only for a
    deliberate administrative correction of the current period."""
    if not user_id or not period:
        return False
    _reject_colon(user_id, "user_id")
    _reject_colon(period, "period")
    budget = max(0, budget_micros)  # never seed a negative budget (would fail-open on reserve)
    key = _user_key(user_id, period)
    if overwrite:
        await redis.set(key, budget)
        return True
    return bool(await redis.set(key, budget, nx=True))


async def seed_mission_cap(
    redis, mission_id: str, budget_micros: int, *, overwrite: bool = False
) -> bool:
    """Seed a mission's fixed autonomy cap — set ONCE at mission creation, never refills on its
    own (the 'budget is a hard safety stop' story: an autonomous mission self-pauses before it can
    drain the user's whole billing budget). SETNX by default so re-creating the same mission_id
    can't silently raise its cap. Returns True iff it wrote."""
    if not mission_id:
        return False
    _reject_colon(mission_id, "mission_id")
    budget = max(0, budget_micros)
    key = _mission_key(mission_id)
    if overwrite:
        await redis.set(key, budget)
        return True
    return bool(await redis.set(key, budget, nx=True))
