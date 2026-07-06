"""The intake config (`settings.IntakeConfig` / `config/backend/intake.yaml`) — the rate-limiter
knobs, D1-migrated out of foundation/vocab/constants.py. Behavior-preserving value lock (== the
numbers the removed RATE_LIMIT_* constants carried) + range/unknown-key validation."""

import pytest
from pydantic import ValidationError

import settings
from settings import IntakeConfig

_BASE = dict(
    rate_limit_window_s=60.0,
    rate_limit_max_requests=30,
    rate_limit_max_tracked_keys=10_000,
    global_rate_limit_window_s=1.0,
    global_rate_limit_max_requests=10,
)


def test_intake_values_are_behavior_preserving():
    i = settings.INTAKE
    assert i.rate_limit_window_s == 60.0
    assert i.rate_limit_max_requests == 30
    assert i.rate_limit_max_tracked_keys == 10_000
    assert i.global_rate_limit_window_s == 1.0
    assert i.global_rate_limit_max_requests == 10


@pytest.mark.parametrize("bad", [
    {"rate_limit_window_s": 0},
    {"rate_limit_max_requests": 0},
    {"rate_limit_max_tracked_keys": 0},
    {"global_rate_limit_window_s": 0},
    {"global_rate_limit_max_requests": 0},
])
def test_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        IntakeConfig(**{**_BASE, **bad})


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        IntakeConfig(**_BASE, bogus=1)
