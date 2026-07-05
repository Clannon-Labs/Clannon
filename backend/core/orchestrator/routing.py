"""
Entropy-advisory routing scorer — STANDALONE and UNWIRED (issue #64, option A).

Turns a query embedding + a set of labeled domain centroids into **structured
evidence** about how the task disperses across capability domains: a relevance
distribution, its Shannon entropy, and how distinct the domains themselves are.

    query vec + domain centroids ─▶ RoutingSignal { entropy, centroid_spread, weights }

⚠ ADVISORY ONLY — the locked owner ruling (2026-07-05) and this module's charter
HARD RULE: this is a *suggestion the orchestrator may consume*, never a decision.
The orchestrator (the reasoning model) makes the final spawn/route call and can
override this evidence entirely. This scorer NEVER fires an expert, NEVER gates
spawn count, and is deliberately **not wired** into the loop — pure math routing is
too fragile for long-running work. It exists to be consumed later as ONE signal
among others. See `docs/ARCHITECTURE.md §7.2`, `SYSTEM_ARCHITECTURE.md` (both say
advisory). If a future step would let this math *decide*, STOP and propose.

It owns no embedding model (that is `core/llm`, a seam this module never imports):
callers hand it vectors. That keeps it a pure, deterministic, testable leaf.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, Field

# Softmax sharpness for turning cosine similarities (a narrow [-1, 1] band) into a
# meaningful relevance distribution. Lower = sharper (a small similarity edge becomes a
# large weight edge). Advisory + unwired, so this is a sensible default to be TUNED when
# the signal is actually consumed — not a tuned production constant.
_DEFAULT_TEMPERATURE = 0.1

# Below this L2 norm a vector is treated as "no direction" (a zero/degenerate embedding):
# cosine is undefined, so we report zero similarity rather than dividing by ~0.
_ZERO_NORM_EPS = 1e-12


# ─── output contract ────────────────────────────────────────────────────────

class DomainWeight(BaseModel):
    """One domain's standing relative to the query. `similarity` is the raw cosine
    (−1..1); `weight` is its share of the softmax relevance distribution (0..1)."""
    domain: str
    similarity: float
    weight: float


class RoutingSignal(BaseModel):
    """ADVISORY structured evidence for the orchestrator's routing decision — NOT a
    command. The orchestrator decides and may override this entirely; this scorer
    never fires an expert and never gates spawn count.

    - `entropy`         — normalized Shannon entropy (0..1) of the weight distribution.
                          ~0 = the query points sharply at ONE domain (focused);
                          ~1 = the query is spread ~evenly across domains (ambiguous/broad).
                          Evidence about dispersion, NOT a spawn count.
    - `centroid_spread` — mean pairwise cosine DISTANCE among the domain centroids
                          (0..~1): how distinct the domains are from each other. Context
                          for reading `entropy` (high entropy over near-identical domains
                          means something different than over well-separated ones).
    - `weights`         — per-domain similarity + normalized weight, sorted desc.
    - `top_domain`      — the single strongest match (advisory), or None when empty.
    - `note`            — a short, human/model-readable summary of the evidence.
    """
    entropy: float
    centroid_spread: float
    weights: list[DomainWeight] = Field(default_factory=list)
    top_domain: str | None = None
    note: str = ""


# ─── math helpers ───────────────────────────────────────────────────────────

def _cosine(q: np.ndarray, c: np.ndarray) -> float:
    """Cosine similarity, safe on a zero-norm vector (→ 0.0, no div-by-zero)."""
    nq = float(np.linalg.norm(q))
    nc = float(np.linalg.norm(c))
    if nq < _ZERO_NORM_EPS or nc < _ZERO_NORM_EPS:
        return 0.0
    return float(np.dot(q, c) / (nq * nc))


def _softmax(sims: np.ndarray, temperature: float) -> np.ndarray:
    """Numerically-stable softmax over similarities with a temperature. A non-positive
    temperature collapses to a hard argmax-ish (all mass on the max); we guard it to a
    tiny positive floor so callers can't trigger a div-by-zero."""
    t = max(temperature, _ZERO_NORM_EPS)
    z = sims / t
    z = z - np.max(z)                     # stability shift; softmax is shift-invariant
    e = np.exp(z)
    total = float(np.sum(e))
    if total < _ZERO_NORM_EPS:            # unreachable in practice, but keep it total
        return np.full(sims.shape, 1.0 / len(sims))
    return e / total


def _shannon_entropy_normalized(weights: np.ndarray) -> float:
    """Shannon entropy of a probability vector, normalized to 0..1 by log(n) so it is
    comparable across roster sizes. n<=1 → 0.0 (a single option has no ambiguity)."""
    n = len(weights)
    if n <= 1:
        return 0.0
    nz = weights[weights > 0]
    h = float(-np.sum(nz * np.log(nz)))
    return h / math.log(n)


def _mean_pairwise_distance(centroids: np.ndarray) -> float:
    """Mean pairwise cosine DISTANCE (1 − cosine) among the domain centroids. 0 when
    fewer than two domains (nothing to be distinct from). Bounded to [0, 1] for a
    clean signal even though raw cosine distance can reach 2 on opposed vectors."""
    n = len(centroids)
    if n < 2:
        return 0.0
    dists: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            dists.append(1.0 - _cosine(centroids[i], centroids[j]))
    d = sum(dists) / len(dists)
    return float(min(max(d, 0.0), 1.0))


# ─── the scorer ─────────────────────────────────────────────────────────────

def score_routing(
    query: Sequence[float],
    centroids: Sequence[tuple[str, Sequence[float]]],
    *,
    temperature: float = _DEFAULT_TEMPERATURE,
) -> RoutingSignal:
    """Score how a query disperses across capability domains — ADVISORY evidence only.

    Args:
        query:      the query embedding (a vector).
        centroids:  labeled domain centroids as (domain_name, vector) pairs — e.g. one
                    per expert domain, each the embedding of that domain's description.
        temperature: softmax sharpness for the relevance distribution (default tuned-later).

    Returns a `RoutingSignal` (see its docstring). Deterministic and pure.

    Raises `ValueError` on a dimension mismatch (a caller-wiring bug — fail loud), but
    degrades gracefully on legitimate data edges: empty centroids → an empty, zero
    signal; a zero-norm vector → zero similarity, not a crash.
    """
    if not centroids:
        return RoutingSignal(entropy=0.0, centroid_spread=0.0, note="no domains to route over")

    q = np.asarray(query, dtype=float)
    labels = [name for name, _ in centroids]
    mat = np.asarray([list(vec) for _, vec in centroids], dtype=float)

    # dimension discipline: a mismatch is a wiring bug, not a runtime data condition.
    if q.ndim != 1:
        raise ValueError(f"query must be a 1-D vector, got shape {q.shape}")
    if mat.ndim != 2 or mat.shape[1] != q.shape[0]:
        raise ValueError(
            f"centroid dim {mat.shape[1:] } does not match query dim ({q.shape[0]},)"
        )

    sims = np.asarray([_cosine(q, c) for c in mat], dtype=float)
    weights = _softmax(sims, temperature)
    entropy = _shannon_entropy_normalized(weights)
    spread = _mean_pairwise_distance(mat)

    ordered = sorted(
        (DomainWeight(domain=labels[i], similarity=float(sims[i]), weight=float(weights[i]))
         for i in range(len(labels))),
        key=lambda w: w.weight,
        reverse=True,
    )
    top = ordered[0].domain if ordered else None

    if entropy < 0.34:
        shape = f"focused on '{top}'"
    elif entropy < 0.67:
        shape = f"leaning to '{top}' with secondary domains"
    else:
        shape = "dispersed across domains"
    note = (
        f"advisory: query looks {shape} "
        f"(entropy={entropy:.2f}, centroid_spread={spread:.2f}); "
        f"the orchestrator decides — this is evidence, not a spawn count"
    )

    return RoutingSignal(
        entropy=entropy,
        centroid_spread=spread,
        weights=ordered,
        top_domain=top,
        note=note,
    )
