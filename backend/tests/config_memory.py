"""The memory config loader (`settings.MemoryConfig` / `config/backend/memory.yaml`).

Locks the placed config values (behavior-preserving — each equals the constant
core/memory used before externalization) and the fail-loud validation, including the
cross-field `dedup >= supersession` invariant. Memory's own tests cover the consumer
swap; this covers the config seam I own.
"""

import pytest
from pydantic import ValidationError

import settings
from settings import MemoryConfig


_TODAY = dict(
    tier_trust={"wiki": 3, "semantic": 2, "episodic": 1, "procedural": 1},
    tier_floor={"wiki": 0.25, "semantic": 0.15, "episodic": 0.15, "procedural": 0.15},
    recency_half_life_s=2592000,
    recency_floor=0.5,
    min_accept_confidence=0.6,
    dedup_similarity=0.97,
    max_content_chars=2000,
    supersession_floor=0.85,
    supersession_timeout_s=5.0,
    embed_retry_after_s=60.0,
    qdrant_request_timeout_s=5,
    graph_max_hops_ceiling=20,
)


# ── behavior-preserving: the placed config equals what core/memory used ────────────────────

def test_memory_values_match_the_previous_hardcoded_defaults():
    m = settings.MEMORY
    assert (m.tier_trust.wiki, m.tier_trust.semantic, m.tier_trust.episodic, m.tier_trust.procedural) == (3, 2, 1, 1)
    assert m.tier_floor.wiki == 0.25 and m.tier_floor.semantic == 0.15
    assert m.recency_half_life_s == 2592000 and m.recency_floor == 0.5
    assert m.min_accept_confidence == 0.6
    assert m.dedup_similarity == 0.97 and m.supersession_floor == 0.85
    assert m.max_content_chars == 2000 and m.supersession_timeout_s == 5.0
    assert m.embed_retry_after_s == 60.0 and m.qdrant_request_timeout_s == 5
    assert m.graph_max_hops_ceiling == 20


def test_memory_hydration_budget_folded_into_budget_config():
    assert settings.BUDGET.default_memory_budget_tokens == 2000
    assert settings.BUDGET.memory_chars_per_token == 4


def test_d1_migrated_memory_knobs_equal_the_foundation_constants():
    # The MEMORY_* group is migrating out of foundation/vocab/constants.py (D1). Until core/memory
    # repoints + the foundation constants are removed, the config value MUST equal the constant —
    # this locks behavior-preservation so the swap is a no-op.
    import foundation.vocab.constants as c
    m = settings.MEMORY
    assert m.read_timeout_s == c.MEMORY_READ_TIMEOUT_S
    assert m.write_timeout_s == c.MEMORY_WRITE_TIMEOUT_S
    assert m.search_top_k == c.MEMORY_SEARCH_TOP_K
    assert m.relevance_floor == c.MEMORY_RELEVANCE_FLOOR
    assert m.distill_max_retries == c.MEMORY_DISTILL_MAX_RETRIES


# ── the cross-field invariant (fail loud, not a silent doc note) ───────────────────────────

def test_dedup_must_not_fall_below_supersession():
    bad = {**_TODAY, "dedup_similarity": 0.80, "supersession_floor": 0.85}  # inverted
    with pytest.raises(ValidationError):
        MemoryConfig(**bad)


def test_dedup_equal_to_supersession_is_allowed():
    ok = {**_TODAY, "dedup_similarity": 0.85, "supersession_floor": 0.85}  # boundary
    MemoryConfig(**ok)  # must not raise


# ── range + extra-key validation ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("override", [
    {"recency_floor": 1.5},           # fraction > 1
    {"graph_max_hops_ceiling": 0},    # must be >= 1
    {"supersession_timeout_s": 0},    # must be > 0
    {"tier_trust": {"wiki": 0, "semantic": 2, "episodic": 1, "procedural": 1}},  # weight must be > 0
])
def test_out_of_range_is_rejected(override):
    with pytest.raises(ValidationError):
        MemoryConfig(**{**_TODAY, **override})


def test_unknown_key_is_rejected():
    with pytest.raises(ValidationError):
        MemoryConfig(**{**_TODAY, "bogus_knob": 1})
