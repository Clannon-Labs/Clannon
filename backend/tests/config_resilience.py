"""Config loader for the resilience area (D1 move D11, config-depth). Locks the placed value
(behavior-preserving — equals the constant the code used before) + the fail-loud validator.
"""

import pytest
from pydantic import ValidationError

import settings
from settings import ResilienceConfig


def test_cb_recovery_timeout_matches_todays_literal():
    assert settings.RESILIENCE.cb_recovery_timeout_s == 30.0


def test_recovery_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        ResilienceConfig(cb_recovery_timeout_s=0.0)
    with pytest.raises(ValidationError):
        ResilienceConfig(cb_recovery_timeout_s=-1.0)


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        ResilienceConfig(cb_recovery_timeout_s=30.0, bogus=1)
