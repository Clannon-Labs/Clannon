"""
Tests for the entropy-advisory routing scorer (core/orchestrator/routing.py).

The scorer is STANDALONE + UNWIRED (issue #64, option A): pure math over a query
vector + labeled domain centroids, producing ADVISORY evidence. These tests pin the
math (focused → low entropy, dispersed → high entropy), the edge cases (empty, single,
zero-norm, dim-mismatch), and the advisory framing — and assert it is not wired.
"""

import math

import pytest

from core.orchestrator.routing import DomainWeight, RoutingSignal, score_routing

# one-hot domain centroids: mutually orthogonal, so cosine cleanly separates them
_ENG = ("engineering", [1.0, 0.0, 0.0])
_RES = ("research", [0.0, 1.0, 0.0])
_MED = ("media", [0.0, 0.0, 1.0])
_ALL = [_ENG, _RES, _MED]


# ─── the distribution & entropy math ───────────────────────────────────────

def test_focused_query_low_entropy_correct_top():
    sig = score_routing([1.0, 0.0, 0.0], _ALL)
    assert isinstance(sig, RoutingSignal)
    assert sig.top_domain == "engineering"
    assert sig.entropy < 0.34, f"a query aligned to one domain should be focused, got {sig.entropy}"
    # the aligned domain carries the dominant weight
    assert sig.weights[0].domain == "engineering"
    assert sig.weights[0].weight > 0.5


def test_uniform_query_high_entropy():
    # equidistant from all three orthogonal domains → maximally ambiguous
    sig = score_routing([1.0, 1.0, 1.0], _ALL)
    assert sig.entropy > 0.9, f"an equidistant query should be dispersed, got {sig.entropy}"
    # all weights ~equal
    ws = [w.weight for w in sig.weights]
    assert max(ws) - min(ws) < 1e-6


def test_entropy_is_normalized_0_to_1():
    for query in ([1.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0.9, 0.4, 0.1], [-1.0, 0.2, 0.3]):
        sig = score_routing(query, _ALL)
        assert 0.0 <= sig.entropy <= 1.0 + 1e-9


def test_weights_form_a_distribution_sorted_desc():
    sig = score_routing([0.9, 0.4, 0.1], _ALL)
    assert abs(sum(w.weight for w in sig.weights) - 1.0) < 1e-9
    weights = [w.weight for w in sig.weights]
    assert weights == sorted(weights, reverse=True), "weights must be sorted descending"


def test_temperature_sharpens_distribution():
    q = [0.9, 0.5, 0.1]
    sharp = score_routing(q, _ALL, temperature=0.05)
    soft = score_routing(q, _ALL, temperature=1.0)
    assert sharp.entropy < soft.entropy, "lower temperature must sharpen (lower entropy)"


# ─── centroid spread (roster domain distinctness) ──────────────────────────

def test_centroid_spread_orthogonal_domains_is_high():
    sig = score_routing([1.0, 0.0, 0.0], _ALL)
    # three mutually orthogonal one-hots → pairwise cosine 0 → distance 1
    assert sig.centroid_spread == pytest.approx(1.0, abs=1e-9)


def test_centroid_spread_identical_domains_is_zero():
    dup = [("a", [1.0, 0.0, 0.0]), ("b", [1.0, 0.0, 0.0])]
    sig = score_routing([1.0, 0.0, 0.0], dup)
    assert sig.centroid_spread == pytest.approx(0.0, abs=1e-9)


# ─── edge cases: degrade gracefully, never crash ───────────────────────────

def test_empty_centroids_returns_zero_signal():
    sig = score_routing([1.0, 0.0], [])
    assert sig.entropy == 0.0
    assert sig.centroid_spread == 0.0
    assert sig.weights == []
    assert sig.top_domain is None
    assert "no domains" in sig.note


def test_single_domain_has_no_ambiguity():
    sig = score_routing([1.0, 0.0, 0.0], [_ENG])
    assert sig.entropy == 0.0            # one option → zero entropy
    assert sig.top_domain == "engineering"
    assert sig.weights[0].weight == pytest.approx(1.0)


def test_zero_norm_query_does_not_crash():
    # a degenerate all-zero embedding → every cosine is 0 → uniform weights, max entropy
    sig = score_routing([0.0, 0.0, 0.0], _ALL)
    assert all(w.similarity == 0.0 for w in sig.weights)
    assert sig.entropy > 0.9
    assert not math.isnan(sig.entropy)


def test_zero_norm_centroid_does_not_crash():
    centroids = [_ENG, ("dead", [0.0, 0.0, 0.0])]
    sig = score_routing([1.0, 0.0, 0.0], centroids)
    dead = next(w for w in sig.weights if w.domain == "dead")
    assert dead.similarity == 0.0
    assert not math.isnan(sig.entropy)


def test_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        score_routing([1.0, 0.0], _ALL)          # query is 2-D, centroids are 3-D


def test_non_1d_query_raises():
    with pytest.raises(ValueError):
        score_routing([[1.0, 0.0, 0.0]], _ALL)   # nested → 2-D query


def test_deterministic():
    q = [0.7, 0.3, 0.1]
    a = score_routing(q, _ALL)
    b = score_routing(q, _ALL)
    assert a.model_dump() == b.model_dump()


# ─── advisory framing (the locked HARD RULE) ───────────────────────────────

def test_signal_is_advisory_evidence_not_a_command():
    sig = score_routing([1.0, 0.0, 0.0], _ALL)
    # the note frames it as advisory evidence, explicitly NOT a spawn count
    assert "advisory" in sig.note.lower()
    assert "evidence" in sig.note.lower()
    # the contract carries NO spawn-count / action field — it cannot command a spawn
    fields = set(RoutingSignal.model_fields)
    assert not (fields & {"spawn_count", "spawn", "action", "fire", "route_to"})


def test_scorer_is_unwired():
    """Guard: the scorer must not be imported by the live loop/gateway — it exists to be
    consumed LATER as one signal, never auto-firing. If this fails, someone wired it;
    that needs a proposal first (the locked advisory-only ruling)."""
    import core.orchestrator.loop as loop_mod
    import registry.capabilities.handler.capability as cap_mod

    for mod in (loop_mod, cap_mod):
        src = mod.__file__
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        assert "routing" not in text and "score_routing" not in text, (
            f"{src} references the routing scorer — it must stay UNWIRED (propose first)"
        )
