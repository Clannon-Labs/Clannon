"""
Real-cost model for the margin budget — pure µ$ arithmetic, no Redis, no I/O.

Converts an LLM call's token usage + wall-clock time into its real cost in integer
micro-dollars (µ$ = USD × 1e6), per decisions B1 (spend is measured in COST, not tokens)
and B2b (infra = flat-per-call + per-second). Prices come from the fail-closed pricing
config; an un-priced model RAISES rather than being counted as free — never undercharge, so
never silently leak margin. Rounds UP (ceil) so a call is never charged less than it cost.

This is the settle-side truth (actual cost once tokens are known). The Redis atomic
reserve/reconcile broker (ADR-0004) consumes this number; it does not recompute cost itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import settings


@dataclass(frozen=True, slots=True)
class ModelCall:
    """One LLM call's cost inputs: which model, tokens each way, wall-clock seconds."""

    model_id: str
    input_tokens: int
    output_tokens: int
    elapsed_s: float = 0.0


def call_cost_micros(call: ModelCall) -> int:
    """Actual real cost of one completed call, in integer µ$ (rounded UP):

        input_tokens × in_price + output_tokens × out_price   (per-model, fail-closed)
        + flat per-call infra + per-second infra × elapsed.

    Raises `KeyError` (via `PRICING.price_for`) if the model has no price — the fail-closed
    guarantee: an un-priced call blocks, never spends free. Negative token counts are a
    caller bug, not a discount, so they're clamped to 0 (a refund path must never make the
    ceiling grow)."""
    price = settings.PRICING.price_for(call.model_id)
    budget = settings.BUDGET
    in_tokens = max(0, call.input_tokens)
    out_tokens = max(0, call.output_tokens)
    elapsed = max(0.0, call.elapsed_s)
    token_micros = (
        in_tokens * price.input_micros_per_token
        + out_tokens * price.output_micros_per_token
    )
    infra_micros = (
        budget.infra_cost_per_call_micros
        + budget.infra_cost_per_second_micros * elapsed
    )
    return ceil(token_micros + infra_micros)
