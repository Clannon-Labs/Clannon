"""
Exceptional Benchmark 1 — Knowledge Evolution (temporal probe)

Probes whether the memory layer can surface BOTH historical state AND current
state when a user preference evolved over time.

Benchmark scenario (CLANNON_V1_ATTENTION_THRESHOLD.md, Exceptional Benchmark 1):
  T_past  : user "prefers Python"      (30 days ago, procedural memory)
  T_recent: user "primarily uses Rust" (now, procedural memory)
  Query   : "programming language preference"

Required shape for a genuine PASS:
  "Historically preferred Python. Current evidence suggests Rust is now primary."

Expected verdict TODAY: PARTIAL
  - The retrieval substrate IS built: vector search, recency-weighted ranking,
    relevance floor, Lagrangian budget allocation, and MemoryItem.created_at
    provenance all work. Both preference entries survive hydration because the
    30-day-old entry still clears the relevance floor after recency weighting.
  - Temporal ordering IS inferable from MemoryItem.created_at if the caller
    knows to sort by it.
  - GAP: MemoryItem has no temporal-validity fields — no valid_until,
    supersedes_id, or is_historical annotation. The "historically X, now Y"
    shape cannot be asserted structurally; it requires caller-side inference.
  - DOCUMENTED RISK: the write-path dedup threshold (_DEDUP_SIMILARITY=0.97)
    does NOT collapse semantically distinct preferences ("Python" vs "Rust")
    because they name different languages and their embeddings differ
    (cosine < 0.97). Near-identical rewrites of the same preference WOULD be
    merged, silently erasing the historical entry — a temporal collapse risk for
    closely-worded contradictions.
  Full temporal-validity support is gated on issue #16 (typed knowledge records).
"""

import asyncio
import time

from foundation import HydrationRequest, MemoryStore, NormalizedInput
from core.memory.manager import MemoryManager, _DEDUP_SIMILARITY, _RECENCY_FLOOR, _RECENCY_HALF_LIFE_S, _RELEVANCE_FLOOR

# ---------------------------------------------------------------------------
# Synthetic fixtures — seeded at module load to keep timestamps stable
# ---------------------------------------------------------------------------

_USER = "e1-probe-synthetic-user"
_NOW = time.time()
_T_PAST = _NOW - _RECENCY_HALF_LIFE_S  # exactly one recency half-life ago

# Expected recency-weighted rank scores (computed from manager constants):
#   PYTHON: raw=0.82, recency=_RECENCY_FLOOR+(1-_RECENCY_FLOOR)*0.5^1=0.75  → rank=0.82*0.75=0.615
#   RUST:   raw=0.85, recency=_RECENCY_FLOOR+(1-_RECENCY_FLOOR)*1.0  ≈1.0   → rank=0.85*1.0  ≈0.850
# Both are above _RELEVANCE_FLOOR, so both survive.
_PYTHON_RAW_SCORE = 0.82
_RUST_RAW_SCORE = 0.85

_PYTHON_HIT = {
    "id": "e1-python-001",
    "score": _PYTHON_RAW_SCORE,
    "content": "User prefers Python. Expressed preference for Python in backend development work.",
    "user_id": _USER,
    "session_id": "session-day-1",
    "confidence": 0.95,
    "trust": 1,
    "tier": MemoryStore.PROCEDURAL.value,
    "created_at": _T_PAST,
}
_RUST_HIT = {
    "id": "e1-rust-002",
    "score": _RUST_RAW_SCORE,
    "content": "User primarily uses Rust. Rust is now the user's main programming language for new projects.",
    "user_id": _USER,
    "session_id": "session-day-30",
    "confidence": 0.95,
    "trust": 1,
    "tier": MemoryStore.PROCEDURAL.value,
    "created_at": _NOW,
}
_FAKE_VECTOR = [0.1] * 768


# ---------------------------------------------------------------------------
# Hermetic stubs
# ---------------------------------------------------------------------------

def _fake_search(tier, user_id, vector, limit=8):
    """Return both preference hits for PROCEDURAL; empty for all other tiers."""
    if user_id != _USER or tier != MemoryStore.PROCEDURAL:
        return []
    return [_PYTHON_HIT, _RUST_HIT]


async def _fake_embed(texts):
    """Fixed 768-dim vector; avoids loading the 500 MB fastembed model."""
    return [_FAKE_VECTOR for _ in texts]


# ---------------------------------------------------------------------------
# Probe runner
# ---------------------------------------------------------------------------

def _run_probe():
    """Patch store + embeddings, run hydrate, return the HydrationPackage."""
    import core.memory.store as _store
    import core.memory.embeddings as _emb

    orig_search = _store.search
    orig_embed = _emb.embed
    try:
        _store.search = _fake_search
        _emb.embed = _fake_embed

        req = HydrationRequest(
            session_id="e1-probe-session",
            user_id=_USER,
            normalized=NormalizedInput(
                modality="text",
                content_type="text/plain",
                content="What is the user's programming language preference?",
            ),
            token_budget=2000,
        )
        return asyncio.run(MemoryManager().hydrate(req))
    finally:
        _store.search = orig_search
        _emb.embed = orig_embed


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

def _verdict(package):
    """
    Derive PASS / PARTIAL / FAIL from the hydration package and enumerate gaps.

    PASS  : both items returned, temporal order preserved, AND temporal-validity
            fields (valid_until / supersedes_id / is_historical) are present.
    PARTIAL: both items returned and temporal order is inferable from created_at,
             but temporal-validity fields are absent.
    FAIL  : history collapsed — only one (or zero) entries returned.
    """
    items = package.items

    # Match on the distinct preference keyword that appears only in one entry.
    # Avoids false matches when one entry mentions both language names.
    python_items = [i for i in items if "prefers Python" in i.content]
    rust_items   = [i for i in items if "primarily uses Rust" in i.content]

    has_history = bool(python_items)
    has_current = bool(rust_items)

    temporal_order_inferable = (
        has_history and has_current
        and python_items[0].created_at < rust_items[0].created_at
    )

    # MemoryItem is a frozen dataclass with __slots__; accessing a non-existent
    # field raises AttributeError → hasattr returns False for all gap fields.
    has_temporal_validity = any(
        hasattr(i, "valid_until") or hasattr(i, "supersedes_id") or hasattr(i, "is_historical")
        for i in items
    )

    gaps = []

    if not has_history:
        gaps.append(
            "HISTORY-COLLAPSED: older 'prefers Python' entry not retrieved — "
            "history is lost"
        )
    if not has_current:
        gaps.append(
            "CURRENT-MISSING: newer 'primarily uses Rust' entry not retrieved"
        )
    if has_history and has_current and not temporal_order_inferable:
        gaps.append(
            "TEMPORAL-ORDER: cannot determine ordering — created_at values are "
            "equal or inverted"
        )
    if not has_temporal_validity:
        gaps.append(
            "NO-TEMPORAL-VALIDITY (gated on #16): MemoryItem carries no "
            "valid_until / supersedes_id / is_historical field; the "
            "'historically Python, now Rust' shape must be inferred from raw "
            "created_at timestamps rather than asserted from structured metadata"
        )

    # Document the write-path dedup risk without requiring real embeddings.
    # _DEDUP_SIMILARITY = 0.97; semantically distinct preferences ('Python' vs
    # 'Rust') have cosine similarity well below this threshold and coexist.
    # Near-identical rewrites of the same preference (e.g. both starting with
    # "user prefers Python") approach the threshold and risk silent collapse.
    gaps.append(
        f"DEDUP-RISK-DOCUMENTED (write-path, not testable without real embeddings): "
        f"threshold={_DEDUP_SIMILARITY}; distinct language names survive dedup; "
        f"near-identical contradictions may be silently merged, erasing history"
    )

    if has_history and has_current and temporal_order_inferable and has_temporal_validity:
        verdict = "PASS"
    elif has_history and has_current and temporal_order_inferable:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    return verdict, gaps


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def _print_report(verdict, gaps, package):
    sep = "-" * 68
    print(f"\n{sep}")
    print("Exceptional Benchmark 1 — Knowledge Evolution")
    print(sep)
    print(f"Verdict : {verdict}")
    print(f"Items   : {len(package.items)} memory entries returned")
    for item in sorted(package.items, key=lambda i: i.created_at):
        age_days = (_NOW - item.created_at) / 86_400
        age_label = f"{age_days:.0f}d ago" if age_days >= 1 else "now"
        print(
            f"  [{item.store.value:10s}] score={item.score:.3f}  "
            f"created={age_label:8s}  {item.content[:60]}"
        )
    print(f"\nGaps ({len(gaps)}):")
    for gap in gaps:
        print(f"  - {gap}")
    print(sep)


# ---------------------------------------------------------------------------
# Pytest entry point
# ---------------------------------------------------------------------------

def test_e1_knowledge_evolution_probe():
    """
    Exceptional Benchmark 1: temporal-validity probe.

    Seeds two contradicting preference memories (Python→Rust) for a synthetic
    user, runs hydrate(), and checks whether both history and current state are
    returned — and whether the returned data carries first-class temporal-validity
    structure.

    The probe is HERMETIC: store.search and embeddings.embed are replaced with
    deterministic stubs; no Qdrant or fastembed model is required.

    Expected verdict: PARTIAL
      - Substrate correct: both entries returned, temporal order inferable.
      - Depth gap (gated on #16): no valid_until / supersedes_id / is_historical.
    """
    package = _run_probe()
    verdict, gaps = _verdict(package)
    _print_report(verdict, gaps, package)

    assert not package.degraded, (
        "Probe must not degrade — hermetic stubs always succeed"
    )

    items = package.items
    python_items = [i for i in items if "prefers Python" in i.content]
    rust_items   = [i for i in items if "primarily uses Rust" in i.content]

    assert python_items, (
        "Historical 'prefers Python' entry not returned — temporal history collapsed"
    )
    assert rust_items, (
        "Current 'primarily uses Rust' entry not returned"
    )
    assert python_items[0].created_at < rust_items[0].created_at, (
        "created_at ordering not preserved — temporal reconstruction impossible"
    )

    # The core gap assertion: no temporal-validity fields on MemoryItem.
    # This is the documented structural gap, not a regression.
    for item in items:
        assert not hasattr(item, "valid_until"), (
            "Unexpected valid_until found — update this probe to check PASS, "
            "and close the #16 gate"
        )
        assert not hasattr(item, "supersedes_id"), (
            "Unexpected supersedes_id found — update this probe to check PASS"
        )
        assert not hasattr(item, "is_historical"), (
            "Unexpected is_historical found — update this probe to check PASS"
        )

    assert verdict == "PARTIAL", (
        f"Expected PARTIAL (both entries surfaced, temporal order preserved, "
        f"depth fields absent per #16). Got {verdict!r}.\nGaps:\n"
        + "\n".join(f"  {g}" for g in gaps)
    )
