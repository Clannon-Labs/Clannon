"""
Redis atomic budget broker — the enforcement implementer behind `foundation.BudgetPort`.

This is the money layer (ADR-0004, PHASE_BATCH_REDIS Part A): every LLM call reserves an
estimated µ$ cost BEFORE it runs and reconciles to actual AFTER. The one guarantee that must
hold is **no overspend under concurrency** — two calls racing against a near-empty budget must
not both pass. The only correct way to get that is to make "check the ceiling AND take from it"
a single indivisible server-side step; a read-then-decrement in Python is the classic
lost-update race, and a bare `DECRBY` is atomic but cannot refuse to go negative. So the
check-and-decrement lives in a **Lua script run via EVAL** — Redis executes it atomically,
nothing interleaves, and it decrements only if sufficient (REDIS_ARCHITECTURE.md §4.2).

Denomination is **integer µ$** throughout (decision B1: spend is measured in real COST, not
tokens — a token count can't express a cost ceiling because per-token rates differ by model and
infra cost isn't token-linked). The caller computes the µ$ estimate via `core.budget.cost`; this
broker is a pure µ$ ledger and never recomputes cost.

Fail-closed everywhere (§4.4 failure stance): if Redis is unreachable we CANNOT check the
ceiling, so `reserve()` refuses the call (raises `BudgetExhausted`) rather than let an
un-reserved LLM call through — a paid product protects its margin over degrading silently. The
snapshot read (`remaining`) fails closed to *empty* (unknown budget → 0, never unlimited) so a
mission pauses rather than runs blind.

Seeding/reset of a period's budget (writing `spend_ceiling_fraction × amount_paid`) is the
billing event's job, behind a reset interface (Stripe deferred) — NOT this broker's surface.
This broker only reserves/reconciles/reads against budgets that already exist.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from math import ceil

import settings
from foundation import BudgetExhausted, BudgetReservation, BudgetScope, TokenBudget

log = logging.getLogger(__name__)

# Reservation records are cleaned up after this long — a crashed process that reserved but
# never reconciled leaves its record to expire (the reserved µ$ stays taken, the margin-safe
# failure: a user is charged the over-estimate, never under). Bounded by the longest a single
# call can run (the whole-turn wall clock), single-sourced from config so it can't drift.
_RESERVATION_TTL_S: int = ceil(settings.ORCHESTRATOR.turn_wall_clock_s)


def _calendar_month_utc() -> str:
    """The billing period key (decision B5: calendar month). UTC so a period boundary is the
    same instant for every user regardless of their timezone."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ── The atomic scripts (the only place a ceiling is checked-and-taken) ────────────────────────

# reserve: check EVERY ceiling in scope, then decrement ALL of them, or NONE. The two checks
# run before either decrement, so a mission-short request never touches the user's budget
# (all-or-nothing, the "never a partial hold" contract). Returns {code, tag}: code ≥ 0 is the
# user's remaining balance after a grant; code < 0 is a refusal, tag names which ceiling.
_RESERVE_LUA = """
local est = tonumber(ARGV[1])
if est < 0 then return {-1, 'invalid_estimate'} end
local has_mission = ARGV[2] == '1'
local ubal = redis.call('GET', KEYS[1])
if ubal == false then return {-1, 'user_missing'} end
ubal = tonumber(ubal)
if ubal < est then return {-1, 'user'} end
if has_mission then
  local mbal = redis.call('GET', KEYS[2])
  if mbal == false then return {-1, 'mission_missing'} end
  if tonumber(mbal) < est then return {-1, 'mission'} end
  redis.call('DECRBY', KEYS[2], est)
end
redis.call('DECRBY', KEYS[1], est)
redis.call('SET', KEYS[3], est, 'EX', tonumber(ARGV[3]))
return {ubal - est, 'ok'}
"""

# reconcile: settle a reservation to actual cost. The reservation-record key is the idempotency
# guard — if it's gone (already settled, or expired) this is a no-op, so a retried reconcile
# can't double-refund. delta = estimated - actual: >0 refunds the over-estimate, <0 charges the
# shortfall (INCRBY a negative), which may push a balance slightly negative — correct, the call
# already happened, and the next reserve is blocked because balance < estimate.
_RECONCILE_LUA = """
local held = redis.call('GET', KEYS[3])
if held == false then return 0 end
local delta = tonumber(held) - tonumber(ARGV[1])
redis.call('INCRBY', KEYS[1], delta)
if ARGV[2] == '1' then redis.call('INCRBY', KEYS[2], delta) end
redis.call('DEL', KEYS[3])
return delta
"""


# ── key layout (period on the user key so a reset is a new key, never a mutate) — module-level so
# the seed/reset side (core.budget.seed) shares ONE source for the format, never a divergent copy.
# Each id-space gets a LITERAL segment (user/mission/resv) so the namespaces are provably disjoint:
# without the `user:` segment, `_user_key("mission", X)` would equal `_mission_key(X)` and a user
# named "mission" could starve a mission's safety cap (security review 2026-07-25, finding 1).
def _user_key(user_id: str, period: str) -> str:
    return f"budget:user:{user_id}:{period}"


def _mission_key(mission_id: str) -> str:
    return f"budget:mission:{mission_id}"


def _resv_key(reservation_id: str) -> str:
    return f"budget:resv:{reservation_id}"


class RedisBudget:
    """`foundation.BudgetPort` over an async Redis client (`redis.asyncio.Redis`, or a
    fakeredis async client in tests). The client is injected so the broker owns no connection
    policy — the same sole-broker shape as `GraphManager` over Kuzu."""

    def __init__(
        self,
        redis_client,
        *,
        period_provider: Callable[[], str] = _calendar_month_utc,
        reservation_ttl_s: int = _RESERVATION_TTL_S,
    ) -> None:
        self._redis = redis_client
        self._period = period_provider
        self._resv_ttl = reservation_ttl_s
        self._reserve = redis_client.register_script(_RESERVE_LUA)
        self._reconcile = redis_client.register_script(_RECONCILE_LUA)

    async def reserve(self, scope: BudgetScope, estimate: int) -> BudgetReservation:
        if not scope.user_id:  # identity-set-once; an unscoped reserve is a bug, fail closed
            raise BudgetExhausted("budget reserve with no user_id", ceiling="user")
        # Validate the estimate AT THIS BOUNDARY regardless of how trusted the caller is meant to
        # be: a negative estimate would flip the Lua DECRBY into a balance-INFLATING increment
        # (fail-OPEN in the one module whose job is to never fail open). A negative reaching here
        # means the cost model produced garbage — refuse loud (ERROR), never silently clamp to a
        # free reservation. (The Lua guards it too; this is the readable, logged front line.)
        if estimate < 0:
            log.error("budget reserve with negative estimate %d — cost model produced garbage", estimate)
            raise BudgetExhausted("negative budget estimate (cost model error)", ceiling="user")
        period = self._period()
        reservation_id = uuid.uuid4().hex
        has_mission = bool(scope.mission_id)
        user_key = _user_key(scope.user_id, period)
        keys = [
            user_key,
            # When there's no mission, the Lua never reads KEYS[2] (guarded by has_mission==0), so
            # any filler is inert — reuse the user key rather than a "budget:mission:_none" sentinel
            # that could (however improbably) collide with a real mission whose id is "_none".
            _mission_key(scope.mission_id) if has_mission else user_key,
            _resv_key(reservation_id),
        ]
        try:
            code, tag = await self._reserve(
                keys=keys, args=[estimate, "1" if has_mission else "0", self._resv_ttl]
            )
        except Exception as exc:  # store unreachable → we could not CHECK the ceiling
            # ERROR, not INFO: an ops fault wearing exhaustion's face (errors.py §"two triggers").
            log.error("budget store unreachable on reserve (fail-closed): %s", exc)
            raise BudgetExhausted("budget store unreachable", cause=exc) from exc
        tag = tag.decode() if isinstance(tag, (bytes, bytearray)) else tag
        if int(code) < 0:
            ceiling = "mission" if tag.startswith("mission") else "user"
            log.info("budget ceiling reached on reserve: %s", tag)
            raise BudgetExhausted(f"{ceiling} budget ceiling reached", ceiling=ceiling)
        return BudgetReservation(reservation_id=reservation_id, scope=scope, estimated=estimate)

    async def reconcile(self, reservation: BudgetReservation, actual: int) -> bool:
        # Never RAISES onto the caller's path (contract unchanged): a reconcile fault is logged
        # here and the caller gets a `False` return instead of an exception. That return value
        # is a SIGNAL for the caller to log more loudly at its own seam (retry.py does) — not a
        # repair. There is no out-of-band Postgres true-up yet (security review 2026-07-26,
        # finding 2), so a `False` here means the reservation may go unrefunded past its TTL if
        # the caller's own retry also fails against the same store fault.
        scope = reservation.scope
        period = self._period()
        has_mission = bool(scope.mission_id)
        user_key = _user_key(scope.user_id, period)
        keys = [
            user_key,
            _mission_key(scope.mission_id) if has_mission else user_key,  # inert filler (Lua guards KEYS[2])
            _resv_key(reservation.reservation_id),
        ]
        try:
            await self._reconcile(keys=keys, args=[max(0, actual), "1" if has_mission else "0"])
            return True
        except Exception as exc:
            log.error("budget reconcile failed (left for out-of-band settle): %s", exc)
            return False

    async def remaining(self, scope: BudgetScope) -> TokenBudget:
        # Advisory snapshot; only reserve() is authoritative. Fails closed to EMPTY (0), never
        # to unlimited — an unknown/unreachable budget must pause work, not wave it through.
        period = self._period()
        try:
            ubal_raw = await self._redis.get(_user_key(scope.user_id, period))
            mbal_raw = (
                await self._redis.get(_mission_key(scope.mission_id))
                if scope.mission_id
                else None
            )
        except Exception as exc:
            log.error("budget store unreachable on remaining (fail-closed to empty): %s", exc)
            return TokenBudget(user_remaining=0, mission_remaining=None, period=period)
        user_remaining = int(ubal_raw) if ubal_raw is not None else 0
        mission_remaining = int(mbal_raw) if mbal_raw is not None else (
            0 if scope.mission_id else None
        )
        return TokenBudget(
            user_remaining=user_remaining, mission_remaining=mission_remaining, period=period
        )
