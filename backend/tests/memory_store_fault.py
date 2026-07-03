"""
Hermetic resilience harness — MemoryManager.hydrate() store-fault behaviour.

Module contract (core/memory/CLAUDE.md NEVER block):
  "Every fault DEGRADES, never fails the run: embeddings/store down => return a
  degraded package with an honest note, never raise into a turn."

Three fault classes exercised with test-double store and embedder.
No network calls.  No paid model calls.  No Qdrant instance required.

Fault classes
-------------
  (a) store.search RAISES mid-query — simulated transient connection error at
      the threaded HTTP call (manager.py:143-146).
  (b) store.is_down() is True on entry — store circuit-breaker is open.
  (c) embeddings.embed RAISES — transient embedding model fault.

KNOWN LATENT GAP — case (a) today PROPAGATES
  asyncio.gather at manager.py:143-146 has no try/except and no
  return_exceptions=True.  A store.search that raises inside asyncio.to_thread
  propagates straight into hydrate(), violating the degrade-never-raise contract.

  Verified by running the real code path with a raising test-double before
  writing this test.  Result: ConnectionError escaped hydrate() uncaught.

  Test (a) is marked @pytest.mark.xfail(strict=True) so:
    TODAY (gap present)  — test body raises => xfailed => suite exits 0.
    AFTER FIX (gap closed) — test body passes => xpass => strict mode requires
      the xfail marker to be removed (enforces cleanup of the annotation).

  A needs-reviewer note with the recommended fix is at the bottom of this file.

Distinct from tests/memory_isolation.py (write-path tenant isolation) and
tests/memory_invisible.py (hydration prefetch + decision-log filtering).
"""
from __future__ import annotations

import asyncio

import pytest

from foundation import (
    HydrationPackage,
    HydrationRequest,
    NormalizedInput,
)
import core.memory.embeddings as _embeddings
import core.memory.store as _store
from core.memory.manager import MemoryManager

# ---------------------------------------------------------------------------
# Per-fault result table — pre-seeded in declaration order so the report
# always shows (a)/(b)/(c) in sequence even when (a) is an xfail.
# ---------------------------------------------------------------------------
_RESULTS: dict[str, str] = {
    "(a) store.search RAISES": "RAISED [ConnectionError] — REAL ROBUSTNESS GAP (xfail)",
    "(b) store.is_down() True": "PENDING",
    "(c) embeddings.embed RAISES": "PENDING",
}

# 768-dim flat vector.  All values identical so cosine similarity to any real
# query is well below the 0.30 relevance floor, keeping per_tier empty and
# routing the is_down / degrade check deterministically.
_FLAT_VECTOR: list[float] = [0.01] * 768


def _req() -> HydrationRequest:
    return HydrationRequest(
        session_id="sess-fault-harness",
        user_id="user-resilience-probe",
        normalized=NormalizedInput(
            modality="text",
            content_type="text/plain",
            content="what do we know about Q3 results?",
        ),
        token_budget=500,
    )


async def _ok_embed(texts: list[str]) -> list[list[float]]:
    """Test-double: successful embed returning correctly shaped vectors."""
    return [_FLAT_VECTOR for _ in texts]


# ---------------------------------------------------------------------------
# (a) store.search RAISES mid-query
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "REAL ROBUSTNESS GAP: asyncio.gather at manager.py:143-146 has no "
        "try/except and no return_exceptions=True.  A store.search that raises "
        "inside asyncio.to_thread propagates out of hydrate() instead of "
        "degrading.  Fix: wrap the gather in a door-level try/except.  "
        "See the needs-reviewer note at the bottom of this file."
    ),
)
def test_a_store_search_raises_degrades(monkeypatch):
    """
    (a) A raising store.search must produce a degraded HydrationPackage,
    never propagate the exception into the caller.

    Precondition: embed succeeds so the code reaches the asyncio.gather.
    The store.search test-double raises ConnectionError on every call.
    """

    def _raising_search(tier, user_id, vector, limit=8):
        raise ConnectionError("simulated transient Qdrant connection timeout")

    monkeypatch.setattr(_store, "search", _raising_search)
    monkeypatch.setattr(_store, "is_down", lambda: False)
    monkeypatch.setattr(_embeddings, "embed", _ok_embed)

    async def go():
        pkg = await MemoryManager().hydrate(_req())
        assert isinstance(pkg, HydrationPackage), (
            "hydrate must return HydrationPackage, not raise"
        )
        assert pkg.degraded, "package must be marked degraded when store faults mid-gather"
        _RESULTS["(a) store.search RAISES"] = "DEGRADED (correct)"

    asyncio.run(go())


# ---------------------------------------------------------------------------
# (b) store.is_down() True on entry — circuit-breaker open
# ---------------------------------------------------------------------------

def test_b_store_is_down_degrades(monkeypatch):
    """
    (b) When is_down() returns True the post-gather check at manager.py:161-168
    must return a degraded package with an honest note, never raise.

    The store.search test-double returns [] (consistent with breaker open);
    embed succeeds so we reach the is_down branch.
    """
    monkeypatch.setattr(_store, "search", lambda *a, **kw: [])
    monkeypatch.setattr(_store, "is_down", lambda: True)
    monkeypatch.setattr(_embeddings, "embed", _ok_embed)

    async def go():
        pkg = await MemoryManager().hydrate(_req())
        assert isinstance(pkg, HydrationPackage), (
            "hydrate must return HydrationPackage, not raise"
        )
        assert pkg.degraded, "package must be marked degraded when store is down"
        assert pkg.notes, "degraded package must carry an honest note"
        _RESULTS["(b) store.is_down() True"] = "DEGRADED (correct)"

    asyncio.run(go())


# ---------------------------------------------------------------------------
# (c) embeddings.embed RAISES — transient embedding fault
# ---------------------------------------------------------------------------

def test_c_embeddings_raises_degrades(monkeypatch):
    """
    (c) A raising embeddings.embed must produce a degraded HydrationPackage;
    _embed_bounded at manager.py:88-103 must catch it and return None so the
    early-exit at manager.py:132-137 fires before any store call.

    The store.search test-double returns [] as a safe fallback (it must not
    be reached when embed faults first, but a non-raising stub keeps the test
    from failing for the wrong reason if the guard path ever changes).
    """

    async def _raising_embed(texts: list[str]) -> list[list[float]]:
        raise OSError("simulated embedding model load failure")

    monkeypatch.setattr(_embeddings, "embed", _raising_embed)
    monkeypatch.setattr(_store, "search", lambda *a, **kw: [])
    monkeypatch.setattr(_store, "is_down", lambda: False)

    async def go():
        pkg = await MemoryManager().hydrate(_req())
        assert isinstance(pkg, HydrationPackage), (
            "hydrate must return HydrationPackage, not raise"
        )
        assert pkg.degraded, "package must be marked degraded when embeddings fault"
        assert pkg.notes, "degraded package must carry an honest note"
        _RESULTS["(c) embeddings.embed RAISES"] = "DEGRADED (correct)"

    asyncio.run(go())


# ---------------------------------------------------------------------------
# Report table — always runs last; always passes
# ---------------------------------------------------------------------------

def test_z_fault_table():
    """
    Print the per-fault DEGRADED / RAISED result table.

    Case (a) is an xfail: its _RESULTS entry is absent when the gap is present
    (the assignment line is never reached before the exception escapes).
    The fallback below inserts the expected RAISED entry so the table is always
    complete regardless of which path the xfail took.
    """
    gap_labels = [k for k, v in _RESULTS.items() if "RAISED" in v]

    width = 62
    print()
    print("=" * width)
    print("  memory store-fault resilience report")
    print("=" * width)
    print(f"  {'Fault class':<38}  Result")
    print("  " + "-" * (width - 2))
    for label, result in _RESULTS.items():
        marker = "!!" if "RAISED" in result else "  "
        print(f"  {marker} {label:<36}  {result}")
    print()
    if gap_labels:
        print(f"  !! {len(gap_labels)} REAL ROBUSTNESS GAP(S) found:")
        for g in gap_labels:
            print(f"       {g}")
        print()
        print("  Recommended fix: door-level try/except around the gather.")
        print("  See the needs-reviewer note at the bottom of this file.")
    else:
        print("  All tested fault classes degrade correctly.")
    print("=" * width)
    print()


# ---------------------------------------------------------------------------
# NEEDS-REVIEWER: manager.py:143-146 degrade-never-raise gap
#
# Location:  backend/core/memory/manager.py, lines 143-146
# Contract:  core/memory/CLAUDE.md NEVER block —
#            "Every fault DEGRADES, never fails the run."
#
# Gap:
#   asyncio.gather is called without return_exceptions=True and without a
#   surrounding try/except:
#
#       tier_hits = await asyncio.gather(
#           *(asyncio.to_thread(store.search, tier, request.user_id,
#                               vectors[0], _SEARCH_K)
#             for tier in inferred)
#       )
#
#   The production store.search wraps all Qdrant calls in try/except and
#   returns [] on any failure, so it NEVER raises today.  However the
#   module's stated contract says every fault must degrade — a defensive
#   door-level wrap is required so that any future change to store.search
#   (or a bug in it) cannot silently break the invariant.
#
# Evidence:
#   test_a_store_search_raises_degrades is marked xfail(strict=True).
#   Verified manually before writing this test: ConnectionError from a
#   raising test-double store.search escaped hydrate() uncaught.
#
# Recommendation:
#   Option 1 (preferred -- minimal, one try/except at the door):
#
#       try:
#           tier_hits = await asyncio.gather(
#               *(asyncio.to_thread(store.search, tier, request.user_id,
#                                   vectors[0], _SEARCH_K)
#                 for tier in inferred)
#           )
#       except Exception as exc:
#           log.warning("memory store fault mid-gather (degrading): %s", exc)
#           return HydrationPackage(
#               items=items, token_budget=budget, degraded=True,
#               notes="memory temporarily unavailable (store error); answering without it",
#           )
#
#   Option 2 (finer-grained, degrade per-tier):
#       Pass return_exceptions=True to gather; skip any tier whose result is
#       an Exception instance rather than aborting the whole call.
#
# Owner:    memory module maintainer
# Priority: High — the degrade-never-raise contract is a production
#           reliability invariant stated in the module's own CLAUDE.md.
#           One try/except closes the gap.
# ---------------------------------------------------------------------------
