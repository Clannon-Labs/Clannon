"""
The token-budget boundary.

The contract the budget CONSUMER (the LLM-call layer at `core/llm/retry.py`, which
reserves before a call and reconciles after) and the budget IMPLEMENTER (a Redis
atomic check-and-decrement, ADR-0004) agree on, so neither imports the other — the
same one-door / sole-broker discipline as `MemoryPort` and `GraphPort`. No caller ever
touches Redis or a raw `DECRBY`; every spend goes through `reserve()`/`reconcile()`.

Ratified 2026-07-05 (backend: seam placement) from the Redis-budget design. This is
the CONTRACT slice only — inert, no implementer yet: the atomic Redis-Lua enforcement,
the `retry.py` anchor, and the `budget_scope` ContextVar land as the #3 build (they
need Redis added as a dependency, proposed separately). The mission ceiling
(`mission_id` / `TokenBudget.mission_remaining`) is designed-in for the Mission Engine
(#4) but inert until then — a user-only scope simply carries no mission ceiling.
Nothing here forces either to be built; it makes the ratified seam concrete so the
implementation has a stable target.

Budget is the MONEY sibling of the whole-turn wall clock (`constants.TURN_WALL_CLOCK_S`,
the TIME bound): both are fail-closed resource bounds on one turn, so a runaway loop
cannot overspend the owner's money or time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BudgetScope:
    """Mandatory, fail-closed scope for every budget operation — mirrors `GraphScope`.

    `user_id` is PRIMARY and mandatory: the billing ceiling is keyed on it (Redis
    `budget:{user_id}:{period}`, ADR-0004). `mission_id` is an OPTIONAL SECOND ceiling
    — when set, a `reserve()` must fit under BOTH the user's billing budget AND the
    mission's cap (all-or-nothing), so an autonomous mission can't drain the user's
    wallet. `mission_id=""` = no mission ceiling (the ordinary interactive turn).

    Both ids enter from trusted `ctx` only, never from model output (identity-set-once).
    Carried per-call by the `budget_scope` ContextVar (the #3 wiring), the same idiom
    as the existing `usage_scope()`.
    """
    user_id: str
    mission_id: str = ""


@dataclass(frozen=True, slots=True)
class TokenBudget:
    """A read-only snapshot of what's left under a scope — the two ceilings.

    `mission_remaining is None` = no mission ceiling in play (a user-only scope).
    Advisory: a snapshot can be stale the instant it is read; only `reserve()` decides
    atomically. Consumed by the mission pre-check (pause a mission that can't afford its
    next step), which lands with the Mission Engine (#4).
    """
    user_remaining: int
    mission_remaining: int | None = None
    period: str = ""            # the billing-period key the user ceiling belongs to


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    """The handle a granted `reserve()` returns, so `reconcile()` can settle real cost.

    `estimated` tokens were atomically decremented up front; `reconcile(actual)` refunds
    the over-estimate (or charges the shortfall). `reservation_id` makes reconcile
    idempotent — replaying it must not double-charge.
    """
    reservation_id: str
    scope: BudgetScope
    estimated: int


@runtime_checkable
class BudgetPort(Protocol):
    """The ONLY way anything spends against a token budget; the Redis implementer is the
    sole broker. Every LLM call reserves before and reconciles after, at the `retry.py`
    choke point — exactly as `MemoryPort` is the one door to Qdrant and `GraphPort` to
    Kuzu. No raw Redis command crosses this door.

    Fail-closed everywhere (ADR-0004): if a ceiling can't cover the estimate, or the
    store can't be reached to check, `reserve()` raises `BudgetExhausted` rather than
    letting the call through — a paid product protects its margin over degrading silently.
    """

    async def reserve(self, scope: BudgetScope, estimate: int) -> BudgetReservation:
        """Atomically check-and-decrement `estimate` against EVERY ceiling in scope (the
        user billing budget, and the mission cap when `mission_id` is set) in ONE
        all-or-nothing server-side operation — concurrent calls cannot both pass a
        near-empty budget (the lost-update race ADR-0004 exists to kill). Returns a
        reservation on success; raises `BudgetExhausted` if any ceiling is short OR the
        store is unreachable (fail-closed)."""
        ...

    async def reconcile(self, reservation: BudgetReservation, actual: int) -> None:
        """Settle a reservation to the ACTUAL tokens used once the call returns: refund
        `estimated - actual` if over-reserved, charge the extra if under. Idempotent on
        `reservation_id` (a retry must not double-settle). Does not raise onto the
        caller's path — a reconcile fault is logged and squared against Postgres truth
        out-of-band, never surfaced onto the response."""
        ...

    async def remaining(self, scope: BudgetScope) -> TokenBudget:
        """Read-only snapshot of the ceilings under scope, for a pre-check (e.g. pause a
        mission that can't afford its next step). Advisory — only `reserve()` is
        authoritative. Fails closed on a store fault (an unknown budget is treated as
        unavailable, never as unlimited)."""
        ...
