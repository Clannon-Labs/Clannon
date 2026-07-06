"""The verifier config (`settings.VerifierConfig` / `config/backend/verifier.yaml`).

D1 slice (placement half): the VERIFIER_* bounds are now in config; consumers repoint next.
Behavior-preserving value lock (== the foundation constants, still present until the repoint).
"""

import pytest
from pydantic import ValidationError

import settings
from settings import VerifierConfig


def test_verifier_values_match_todays_constants():
    import foundation.vocab.constants as c
    v = settings.VERIFIER
    assert v.timeout_s == c.VERIFIER_TIMEOUT_S == 12.0
    assert v.max_tokens == c.VERIFIER_MAX_TOKENS == 512
    assert v.max_retries == c.VERIFIER_MAX_RETRIES == 2


@pytest.mark.parametrize("bad", [{"timeout_s": 0}, {"max_tokens": 0}, {"max_retries": -1}])
def test_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        VerifierConfig(**{"timeout_s": 12.0, "max_tokens": 512, "max_retries": 2, **bad})


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        VerifierConfig(timeout_s=12.0, max_tokens=512, max_retries=2, bogus=1)
