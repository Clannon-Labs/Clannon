"""
core.budget — the real-cost margin budget domain.

Contains the pure µ$ cost model plus the Redis atomic reserve/reconcile broker behind
`foundation.BudgetPort` (ADR-0004). Enforcement is built but remains off by default until
pricing, seeding, billing-period, recovery, and security gates are green. Kept separate
from pipeline stages: budget is a resource bound, not a stage.
"""
from core.budget.context import budget_exempt_scope, budget_user_scope, current_scope, get_broker
from core.budget.cost import ModelCall, call_cost_micros, estimate_call_cost_micros
from core.budget.seed import ceiling_micros, seed_mission_cap, seed_user_period

__all__ = [
    "ModelCall", "call_cost_micros", "estimate_call_cost_micros",
    "ceiling_micros", "seed_user_period", "seed_mission_cap",
    "budget_user_scope", "budget_exempt_scope", "current_scope", "get_broker",
]
