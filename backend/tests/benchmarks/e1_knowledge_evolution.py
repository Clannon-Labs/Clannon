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

Expected verdict TODAY: PASS
  - The retrieval substrate IS built: vector search, recency-weighted ranking,
    relevance floor, Lagrangian budget allocation, and MemoryItem.created_at
    provenance all work. Both preference entries survive hydration because the
    30-day-old entry still clears the relevance floor after recency weighting.
  - Temporal ordering IS inferable from MemoryItem.created_at if the caller
    knows to sort by it.
  - CLOSED (EB1): MemoryItem carries first-class temporal-validity fields —
    `valid_at` (CB1) and `superseded_by` (EB1, manager-owned — an LLM judge
    marks a memory superseded by a later one on the write path; fail-closed, see
    core/memory/writer.py::judge_supersession). The fixtures below simulate that
    judge having already run: the Python entry carries
    `superseded_by="e1-rust-002"`. Retrieval keeps the superseded entry
    SURFACED (temporal truth, not erasure) — this probe is READ-SIDE ONLY: it
    asserts hydrate() propagates pre-set fields correctly, it does not exercise
    the judge itself (covered by tests/memory_supersession.py).
  - DOCUMENTED RISK (still open, orthogonal to EB1): the write-path dedup
    threshold (_DEDUP_SIMILARITY=0.97) does NOT collapse semantically distinct
    preferences ("Python" vs "Rust") because they name different languages and
    their embeddings differ (cosine < 0.97). Near-identical rewrites of the same
    preference WOULD be merged, silently erasing the historical entry instead of
    going through the supersession judge — a temporal collapse risk for
    closely-worded contradictions that EB1's judge (a genuinely NEW insert, not
    a dedup-merge) does not apply to.
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
    # EB1: simulates the write-side judge having already marked this superseded
    # by the Rust entry below (id known only to this fixture — MemoryItem itself
    # carries no id field, so the read-side check compares against this literal).
    "valid_at": _T_PAST,
    "superseded_by": "e1-rust-002",
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
    "valid_at": _NOW,
    "superseded_by": "",  # current — nothing has replaced it
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
            fields (valid_at / superseded_by) carry real, correct VALUES — not
            just present on the contract, but populated and readable through
            hydrate() (CB1's valid_at, EB1's superseded_by).
    PARTIAL: both items returned and temporal order is inferable from created_at,
             but temporal-validity fields are absent or unpopulated.
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

    # Real fields, real VALUES — not `hasattr` (every MemoryItem always has these
    # attributes; the old check tested for the wrong names entirely and could
    # never fire). The Python entry must be dated AND marked superseded BY the
    # Rust entry's known id; the Rust entry must be dated and NOT superseded.
    has_temporal_validity = (
        has_history and has_current
        and python_items[0].valid_at > 0.0
        and rust_items[0].valid_at > 0.0
        and python_items[0].superseded_by == _RUST_HIT["id"]
        and rust_items[0].superseded_by == ""
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
            "NO-TEMPORAL-VALIDITY: valid_at/superseded_by absent or unpopulated "
            "on hydrate()'s output; the 'historically Python, now Rust' shape "
            "must be inferred from raw created_at timestamps rather than "
            "asserted from structured metadata"
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
    deterministic stubs; no Qdrant or fastembed model is required. It is
    READ-SIDE ONLY — the fixtures pre-set valid_at/superseded_by as if EB1's
    write-side judge had already run (that judge itself is covered by
    tests/memory_supersession.py); this probe proves hydrate() propagates the
    real values correctly, keeping the superseded entry SURFACED rather than
    erased.

    Expected verdict: PASS
      - Substrate correct: both entries returned, temporal order inferable.
      - Depth (EB1): valid_at + superseded_by carry real values through hydrate().
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

    # The core depth assertion: valid_at + superseded_by carry real VALUES
    # through hydrate(), not just attribute presence (every MemoryItem always
    # has these attributes by contract — checking hasattr alone could never
    # fail, which is exactly why the old version of this probe was dead).
    assert python_items[0].valid_at > 0.0, (
        "historical entry's valid_at not propagated through hydrate()"
    )
    assert rust_items[0].valid_at > 0.0, (
        "current entry's valid_at not propagated through hydrate()"
    )
    assert python_items[0].superseded_by == _RUST_HIT["id"], (
        "historical entry must carry superseded_by pointing at the memory that "
        f"replaced it (expected {_RUST_HIT['id']!r}, got {python_items[0].superseded_by!r})"
    )
    assert rust_items[0].superseded_by == "", (
        "current entry must NOT be marked superseded"
    )
    # Temporal truth, not erasure: the superseded entry must still be there.
    assert python_items, "the superseded entry must stay SURFACED, not be filtered out"

    assert verdict == "PASS", (
        f"Expected PASS (both entries surfaced, temporal order preserved, "
        f"valid_at/superseded_by populated with real values). Got {verdict!r}.\nGaps:\n"
        + "\n".join(f"  {g}" for g in gaps)
    )
