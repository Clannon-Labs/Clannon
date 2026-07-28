"""The typed budget config loader (`settings.py`) + `config/backend/budget.yaml`.

Proves three things the CENTRAL_CONFIG + Redis-budget briefs require:
  1. Behavior-preserving externalization — the values equal what the code used before.
  2. Fail-loud validation — an out-of-range or malformed money knob is rejected at load,
     never run silently wrong (LAW 5).
  3. Single source of truth for the margin ceiling — `SPEND_CEILING_FRACTION` is defined
     in exactly one place and read from config; nothing hardcodes or re-derives it (LAW 4,
     the invariant the Redis budget will enforce).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

import settings
from settings import BudgetConfig


# ── 1. behavior-preserving: the externalized values equal the old hardcoded ones ──────────

def test_budget_values_match_the_previous_hardcoded_defaults():
    # These were the literals in api/run_driver.py before externalization — the move changes
    # WHERE the value lives, never WHAT it is.
    assert settings.BUDGET.history_char_budget == 200_000
    assert settings.BUDGET.verbatim_turn_floor == 2
    assert settings.BUDGET.usage_metering_window_days == 30   # D10: was hardcoded window=30 in app.py


def test_spend_ceiling_is_the_ruled_default():
    # D2 ruling (2026-07-05): SPEND_CEILING_FRACTION = 0.80 → ≥20% guaranteed margin.
    assert settings.SPEND_CEILING_FRACTION == 0.80
    assert settings.BUDGET.spend_ceiling_fraction == settings.SPEND_CEILING_FRACTION


def test_run_driver_reads_the_budget_from_config():
    # The consumer now sources its constants from the loader (not a private literal).
    from api import run_driver

    assert run_driver._HISTORY_CHAR_BUDGET == settings.BUDGET.history_char_budget
    assert run_driver._VERBATIM_TURN_FLOOR == settings.BUDGET.verbatim_turn_floor


def test_enforcement_is_off_by_default():
    # The retry.py anchor must be inert until the owner flips this (real prices + seeding
    # aren't in place yet — see proposals/to-owner/2026-07-28_budget-prices-and-go-live.md).
    assert settings.BUDGET.enforcement_enabled is False


def test_estimate_knobs_are_positive():
    assert settings.BUDGET.media_token_estimate_per_item > 0
    assert settings.BUDGET.output_token_estimate_fallback > 0
    assert settings.BUDGET.redis_url


# ── 2. fail-loud validation: a bad money knob never loads silently ────────────────────────

@pytest.mark.parametrize("bad_fraction", [0.0, -0.1, 1.01, 2.0])
def test_ceiling_out_of_range_is_rejected(bad_fraction):
    # 0 < f ≤ 1 — a fraction that would erase our margin (≥1) or make no sense (≤0) is refused.
    with pytest.raises(ValidationError):
        BudgetConfig(spend_ceiling_fraction=bad_fraction, history_char_budget=1, verbatim_turn_floor=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"spend_ceiling_fraction": 0.8, "history_char_budget": 0, "verbatim_turn_floor": 1},   # budget must be > 0
        {"spend_ceiling_fraction": 0.8, "history_char_budget": 100, "verbatim_turn_floor": 0}, # floor must be ≥ 1
    ],
)
def test_other_knobs_are_range_checked(kwargs):
    with pytest.raises(ValidationError):
        BudgetConfig(**kwargs)


def test_unknown_key_is_rejected():
    # extra="forbid": a typo'd or stray key in budget.yaml fails loud rather than being ignored.
    with pytest.raises(ValidationError):
        BudgetConfig(
            spend_ceiling_fraction=0.8, history_char_budget=100, verbatim_turn_floor=1, celiing=0.9
        )


# ── 3. single source of truth for the margin ceiling (grep/import proof) ──────────────────

def _backend_py_files() -> list[Path]:
    root = Path(settings.__file__).resolve().parent  # backend/
    return [
        p for p in root.rglob("*.py")
        if ".venv" not in p.parts and "__pycache__" not in p.parts
    ]


def test_spend_ceiling_fraction_is_defined_in_exactly_one_module():
    # The name is *assigned* only in settings.py; every other reference must be a READ of
    # settings.SPEND_CEILING_FRACTION — never a second definition or a hardcoded copy.
    definers = [
        p for p in _backend_py_files()
        if any(
            line.lstrip().startswith("SPEND_CEILING_FRACTION") and "=" in line
            and "==" not in line.split("=")[0] + "="
            for line in p.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert definers == [Path(settings.__file__).resolve()], (
        f"the margin ceiling must be defined only in settings.py; also assigned in: {definers}"
    )


def test_ceiling_fraction_is_only_configured_in_budget_yaml():
    # The raw fraction key lives in exactly one config file; the loader reads it, code doesn't
    # re-declare it. (Guards against a future call site sprouting its own `spend_ceiling_fraction`.)
    root = Path(settings.__file__).resolve().parent.parent  # repo root
    hits = [
        p for p in root.rglob("*.yaml")
        if ".venv" not in p.parts and "spend_ceiling_fraction" in p.read_text(encoding="utf-8")
    ]
    assert hits == [root / "config" / "backend" / "budget.yaml"], (
        f"spend_ceiling_fraction must live only in config/backend/budget.yaml; found in: {hits}"
    )
