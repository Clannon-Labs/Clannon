"""The pure µ$ cost model (`core.budget.cost`) + pricing config (`settings.PRICING`).

Proves the real-cost arithmetic (B1), the flat+per-second infra (B2b), fail-closed pricing
(B3 — an un-priced model blocks, never charges free), and round-UP (never undercharge).
No Redis here — this is the settle-side cost truth the atomic broker will consume.
"""

import pytest
from pydantic import ValidationError

import settings
from core.budget import call_cost_micros, ModelCall
from settings import ModelPrice, PricingConfig


# ── the cost arithmetic ───────────────────────────────────────────────────────────────────

def test_call_cost_is_tokens_times_price_plus_flat_infra():
    # haiku placeholder: in 0.80, out 4.00 µ$/tok; infra flat 50, per-sec 20 (elapsed 0).
    # 1000×0.80 + 500×4.00 + 50 + 0 = 800 + 2000 + 50 = 2850 µ$.
    cost = call_cost_micros(ModelCall("claude-haiku-4-5", input_tokens=1000, output_tokens=500))
    assert cost == 2850


def test_per_second_infra_is_charged():
    base = call_cost_micros(ModelCall("claude-haiku-4-5", 1000, 500, elapsed_s=0))
    with_time = call_cost_micros(ModelCall("claude-haiku-4-5", 1000, 500, elapsed_s=3))
    assert with_time - base == 3 * settings.BUDGET.infra_cost_per_second_micros  # 60 µ$


def test_cost_rounds_up_never_undercharges():
    # gemini-flash-lite in 0.10 µ$/tok: 5 input tokens = 0.50 µ$ token cost; + flat 50 = 50.5
    # → must ceil to 51, never floor to 50 (undercharging erodes margin).
    cost = call_cost_micros(ModelCall("gemini-2.5-flash-lite", input_tokens=5, output_tokens=0))
    assert cost == 51


def test_negative_tokens_are_clamped_not_credited():
    # a bad -100 must never REDUCE cost below the infra floor (a refund can't grow the ceiling).
    cost = call_cost_micros(ModelCall("claude-haiku-4-5", input_tokens=-100, output_tokens=-100))
    assert cost == settings.BUDGET.infra_cost_per_call_micros  # 50, tokens floored to 0


# ── fail-closed pricing (B3) ──────────────────────────────────────────────────────────────

def test_unpriced_model_raises_never_free():
    with pytest.raises(KeyError):
        call_cost_micros(ModelCall("some-unlisted-model-v9", 100, 100))


def test_price_for_known_model_returns_rate():
    p = settings.PRICING.price_for("claude-sonnet-4-6")
    assert p.input_micros_per_token == 3.00 and p.output_micros_per_token == 15.00


# ── config validation ─────────────────────────────────────────────────────────────────────

def test_pricing_loaded_and_covers_the_default_primary_models():
    # The default-routed models (models.yaml defaults) must be priced, or those calls block.
    for m in ("claude-haiku-4-5", "claude-sonnet-4-6", "gpt-5.4", "gemini-2.5-flash"):
        assert m in settings.PRICING.models


def test_negative_price_is_rejected():
    with pytest.raises(ValidationError):
        ModelPrice(input_micros_per_token=-1.0, output_micros_per_token=1.0)


def test_pricing_extra_key_is_rejected():
    with pytest.raises(ValidationError):
        PricingConfig(models={}, bogus=1)


def test_infra_knobs_present_and_nonnegative():
    assert settings.BUDGET.infra_cost_per_call_micros >= 0
    assert settings.BUDGET.infra_cost_per_second_micros >= 0
