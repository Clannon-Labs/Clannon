"""
core.budget — the real-cost margin budget domain.

Today: the pure µ$ cost model (`cost.py`) — token usage + time → integer micro-dollars,
fail-closed on an un-priced model. Later: the Redis atomic reserve/reconcile broker behind
`foundation.BudgetPort` (ADR-0004), which consumes these cost numbers but never recomputes
them. Kept separate from the pipeline stages: budget is a resource bound, not a stage.
"""
from core.budget.cost import ModelCall, call_cost_micros
from core.budget.seed import ceiling_micros, seed_mission_cap, seed_user_period

__all__ = [
    "ModelCall", "call_cost_micros",
    "ceiling_micros", "seed_user_period", "seed_mission_cap",
]
