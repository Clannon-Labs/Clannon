"""
UnlimitedBudget — the Mission Engine's swap seam until backend's real Redis-backed
budget anchor lands (docs/architecture/BUDGET_ENFORCEMENT_ANCHOR.md), ratified
2026-07-25 (proposals/archive/to-backend/2026-07-25_mission-engine-loop-wiring-design.md
§3).

`run_operate_step`'s §7 pre-check calls `BudgetPort.remaining()` unconditionally.
`RedisBudget.remaining()` fails CLOSED to an EMPTY budget when the store is
unreachable (core/budget/redis_budget.py) — and today, in every environment,
Redis isn't seeded and the enforcement flag doesn't exist yet. Wiring the real
broker in (or leaving `Ports.budget` unset) would BUDGET_PAUSE every mission on
its very first step, everywhere, before the anchor ever ships.

This is "enforcement OFF" made concrete at the Mission Engine's one touchpoint —
the exact default posture the anchor doc already commits to — not a parallel
budget system. `reserve()`/`reconcile()` are implemented (the Protocol requires
them) but nothing in this module's call path uses them; only `remaining()` is
read by `run_operate_step`'s pre-check. When the real anchor + enforcement flag +
seeding land, swapping `Ports.budget` from this stub to the real broker is a
one-line `wiring.py` change (backend's call — the same broker instance then
serves both this pre-check and the retry.py per-call anchor).
"""

from __future__ import annotations

from uuid import uuid4

from foundation import BudgetReservation, BudgetScope, TokenBudget

# Large enough that no realistic estimate ever exceeds it; mission_remaining=None
# (below) already means "no mission ceiling in play" per TokenBudget's own
# docstring, so this value only has to clear the user-ceiling check.
_UNLIMITED = 2**31


class UnlimitedBudget:
    """Satisfies BudgetPort in full; never constrains anything."""

    async def reserve(self, scope: BudgetScope, estimate: int) -> BudgetReservation:
        return BudgetReservation(reservation_id=uuid4().hex, scope=scope, estimated=estimate)

    async def reconcile(self, reservation: BudgetReservation, actual: int) -> None:
        return None

    async def remaining(self, scope: BudgetScope) -> TokenBudget:
        return TokenBudget(user_remaining=_UNLIMITED, mission_remaining=None)
