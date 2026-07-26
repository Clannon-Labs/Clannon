"""
Per-call budget identity — the ContextVars the enforcement anchor (`core/llm/retry.py`) reads
to build a `BudgetScope`, plus the lazy broker singleton it reserves/reconciles against.

`user_id` is set ONCE per turn at the authenticated `api/` entry (`budget_user_scope`,
alongside the existing `usage_scope()`) and is safe as a ContextVar: pydantic-ai copies the
context when it fans tool calls out via `asyncio.gather`/`create_task`, but `user_id` never
changes mid-turn, so every child task sees the same value regardless of when it was spawned.

`mission_id` is deliberately NOT a ContextVar here (see
`docs/architecture/BUDGET_ENFORCEMENT_ANCHOR.md` resolution #2). A turn CAN become a mission
mid-flight, and a ContextVar `.set()` inside one child task is invisible to sibling/later tasks
in the same asyncio fan-out — a mission-id ContextVar would reintroduce exactly the staleness
that sank the first design. Instead `core/llm/framework.py` reads `deps.ctx.mission_id` LIVE at
each call site (the same place `budget_model_id`'s estimate is built) and passes it straight
through to `run_agent`, so there is nothing here that can go stale.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

import settings
from foundation import BudgetPort, BudgetScope

_USER_ID: ContextVar[str] = ContextVar("vraksha_budget_user_id", default="")
_EXEMPT: ContextVar[bool] = ContextVar("vraksha_budget_exempt", default=False)


@contextmanager
def budget_user_scope(user_id: str) -> Iterator[None]:
    """Set the billing identity for every LLM call made within this turn. Call once at the
    authenticated api/ entry, alongside `usage_scope()` — never sourced from model output."""
    token = _USER_ID.set(user_id or "")
    try:
        yield
    finally:
        _USER_ID.reset(token)


@contextmanager
def budget_exempt_scope() -> Iterator[None]:
    """Mark an intentional unscoped call (an internal script/CLI path outside the api/ turn,
    e.g. `main.py`'s REPL or `scripts/prompt_regression.py`) so the anchor skips it quietly
    instead of logging a wiring-bug ERROR when enforcement is on."""
    token = _EXEMPT.set(True)
    try:
        yield
    finally:
        _EXEMPT.reset(token)


def current_scope(mission_id: str = "") -> BudgetScope | None:
    """The live `BudgetScope` for a reserve, or `None` when this call is out of scope
    (explicitly exempt, or no `user_id` set). The caller decides how `None` should be treated —
    e.g. a quiet skip for an exempt call vs. a loud ERROR for a genuine wiring gap."""
    if _EXEMPT.get():
        return None
    user_id = _USER_ID.get()
    if not user_id:
        return None
    return BudgetScope(user_id=user_id, mission_id=mission_id or "")


def is_exempt() -> bool:
    """Whether the current call is explicitly opted out (vs. merely missing a scope)."""
    return _EXEMPT.get()


@lru_cache(maxsize=1)
def _broker_singleton() -> BudgetPort | None:
    """Lazily build the real Redis-backed broker — ONLY when enforcement is on. While
    `settings.BUDGET.enforcement_enabled` is False (the default), this never imports `redis` or
    touches a connection, so the OFF path is fully inert."""
    if not settings.BUDGET.enforcement_enabled:
        return None
    import redis.asyncio as redis_asyncio  # imported lazily: no Redis dep on the OFF path

    from core.budget.redis_budget import RedisBudget

    client = redis_asyncio.Redis.from_url(settings.BUDGET.redis_url)
    return RedisBudget(client)


def get_broker() -> BudgetPort | None:
    """The active budget broker, or `None` when enforcement is off. Tests that want a fake
    broker monkeypatch this function directly rather than the (real, Redis-touching) singleton
    it wraps."""
    return _broker_singleton()
