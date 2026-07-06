"""The LLM retry config (`settings.LlmConfig` / `config/backend/llm.yaml`).

D1 slice: the LLM_* retry/backoff bounds moved out of foundation/vocab/constants.py to
config; core/llm/retry.py reads settings.LLM.*. Behavior-preserving value lock + validation.
"""

import pytest
from pydantic import ValidationError

import settings
from settings import LlmConfig


def test_llm_values_match_todays_literals():
    m = settings.LLM
    assert m.transient_max_retries == 2
    assert m.fallback_max_retries == 1
    assert m.retry_base_delay_s == 2.0
    assert m.retry_max_delay_s == 30.0


def test_retry_py_reads_from_settings_not_foundation():
    # The LLM_* constants are GONE from foundation — retry.py must source from settings.LLM.
    import foundation.vocab.constants as c
    assert not hasattr(c, "LLM_TRANSIENT_MAX_RETRIES")
    from core.llm import retry  # imports cleanly (would ImportError if it still used the constant)
    assert retry is not None


@pytest.mark.parametrize("bad", [
    {"transient_max_retries": -1},   # >= 0
    {"retry_base_delay_s": 0},       # > 0
    {"retry_max_delay_s": -5.0},     # > 0
])
def test_out_of_range_rejected(bad):
    base = dict(transient_max_retries=2, fallback_max_retries=1, retry_base_delay_s=2.0, retry_max_delay_s=30.0)
    with pytest.raises(ValidationError):
        LlmConfig(**{**base, **bad})


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        LlmConfig(transient_max_retries=2, fallback_max_retries=1, retry_base_delay_s=2.0,
                  retry_max_delay_s=30.0, bogus=1)
