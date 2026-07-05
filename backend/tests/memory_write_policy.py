"""
Hermetic harness: memory WRITE-DOOR persistence policy.

Drives MemoryManager.record_write_proposals() with monkeypatched test-double
store + embedder (no live Qdrant, no network, no paid keys).  Uses the manager's
REAL constants and branches (core/memory/manager.py:225-267).

Policy assertions:
  (a) WORKING tier — never persisted (no embed, no upsert)
  (b) WIKI tier — redirected to SEMANTIC on write; upserted with SEMANTIC trust
  (c) SEMANTIC/PROCEDURAL below _MIN_ACCEPT_CONFIDENCE — dropped;
      EPISODIC (no confidence gate) — always persisted
  (d) empty/whitespace content — skipped; over-long — truncated to _MAX_CONTENT_CHARS
  (e) embedder returns no vector — drops quietly, no upsert, no raise
  (f) dedup: near-identical existing hit refreshes existing point_id (max confidence);
      dissimilar hit inserts new (point_id=None)
  (g) fail-closed scope: empty/None user_id OR empty proposals — no embed, no upsert
  (h) every upsert scoped to caller user_id + correct tier + _TIER_TRUST

On any genuine divergence from the documented policy this harness REPORTS a gap
(writes to ~/.clannon_proposal) rather than editing manager.py.
"""

from __future__ import annotations

import asyncio

import pytest

import core.memory.embeddings as emb_mod
import core.memory.store as store_mod
from core.memory.manager import (
    MemoryManager,
    _DEDUP_SIMILARITY,
    _MAX_CONTENT_CHARS,
    _MIN_ACCEPT_CONFIDENCE,
    _TIER_TRUST,
)
from foundation import MemoryStore, MemoryWriteProposal


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

_DUMMY_VEC: list[float] = [0.1] * 768


class _Recorder:
    """Sync callable wired in place of store.upsert; records every call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(
        self,
        tier: MemoryStore,
        *,
        user_id: str,
        session_id: str,
        trace_id: str,
        vector: list[float],
        content: str,
        rationale: str,
        confidence: float,
        trust: int,
        point_id: str | None = None,
        kind: str = "unspecified",
        valid_at: float = 0.0,
        source: str = "",
        superseded_by: str = "",
        participants: str = "",
    ) -> str:
        self.calls.append(
            dict(
                tier=tier,
                user_id=user_id,
                content=content,
                confidence=confidence,
                trust=trust,
                point_id=point_id,
                kind=kind,
                valid_at=valid_at,
                source=source,
            )
        )
        return "fake-id"


class _EmbedTripwire:
    """Async callable that FAILS the test if invoked (proves early-return paths)."""

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError(
            "embeddings.embed must NOT be called in this execution path"
        )


def _embed_ok():
    async def embed(texts: list[str]) -> list[list[float]]:
        return [_DUMMY_VEC for _ in texts]

    return embed


def _embed_down():
    async def embed(texts: list[str]) -> list[list[float]]:
        return []

    return embed


def _search_miss():
    def search(
        tier: MemoryStore, user_id: str, vector: list[float], limit: int
    ) -> list[dict]:
        return []

    return search


def _search_hit(score: float, existing_id: str = "existing-id", existing_conf: float = 0.5):
    def search(
        tier: MemoryStore, user_id: str, vector: list[float], limit: int
    ) -> list[dict]:
        return [{"id": existing_id, "score": score, "confidence": existing_conf}]

    return search


def _p(
    store: MemoryStore = MemoryStore.EPISODIC,
    content: str = "Some durable content.",
    confidence: float = 0.9,
    rationale: str = "",
) -> MemoryWriteProposal:
    return MemoryWriteProposal(
        store=store, content=content, confidence=confidence, rationale=rationale
    )


# ---------------------------------------------------------------------------
# _run helper — patches doubles then drives record_write_proposals
# ---------------------------------------------------------------------------

async def _run(
    user_id: str,
    proposals: list[MemoryWriteProposal],
    *,
    monkeypatch,
    embed_fn=None,
    search_fn=None,
    recorder: _Recorder | None = None,
) -> _Recorder:
    rec = recorder or _Recorder()
    monkeypatch.setattr(emb_mod, "embed", embed_fn or _embed_ok())
    monkeypatch.setattr(store_mod, "search", search_fn or _search_miss())
    monkeypatch.setattr(store_mod, "upsert", rec)
    m = MemoryManager()
    await m.record_write_proposals(user_id, "sess-test", proposals)
    return rec


# ---------------------------------------------------------------------------
# (a) WORKING tier — never persisted
# ---------------------------------------------------------------------------


def test_working_tier_never_persisted(monkeypatch):
    rec = asyncio.run(_run("u1", [_p(store=MemoryStore.WORKING)], monkeypatch=monkeypatch))
    assert not rec.calls, "WORKING tier must never produce an upsert"


# ---------------------------------------------------------------------------
# (b) WIKI tier — redirected to SEMANTIC, correct trust
# ---------------------------------------------------------------------------


def test_wiki_tier_redirected_to_semantic(monkeypatch):
    rec = asyncio.run(
        _run(
            "u1",
            [MemoryWriteProposal(store=MemoryStore.WIKI, content="A fact.", confidence=0.95)],
            monkeypatch=monkeypatch,
        )
    )
    assert len(rec.calls) == 1, "WIKI proposal must produce one upsert"
    call = rec.calls[0]
    assert call["tier"] is MemoryStore.SEMANTIC, "WIKI must be redirected to SEMANTIC tier on write"
    assert call["trust"] == _TIER_TRUST[MemoryStore.SEMANTIC], (
        "redirected WIKI upsert must carry SEMANTIC trust value"
    )
    assert call["user_id"] == "u1"


# ---------------------------------------------------------------------------
# (c) Confidence gate
# ---------------------------------------------------------------------------


def test_semantic_below_confidence_floor_dropped(monkeypatch):
    low = _MIN_ACCEPT_CONFIDENCE - 0.01
    rec = asyncio.run(_run("u1", [_p(store=MemoryStore.SEMANTIC, confidence=low)], monkeypatch=monkeypatch))
    assert not rec.calls, f"SEMANTIC at confidence {low} must be dropped (floor={_MIN_ACCEPT_CONFIDENCE})"


def test_procedural_below_confidence_floor_dropped(monkeypatch):
    low = _MIN_ACCEPT_CONFIDENCE - 0.01
    rec = asyncio.run(_run("u1", [_p(store=MemoryStore.PROCEDURAL, confidence=low)], monkeypatch=monkeypatch))
    assert not rec.calls, f"PROCEDURAL at confidence {low} must be dropped (floor={_MIN_ACCEPT_CONFIDENCE})"


def test_semantic_at_confidence_floor_passes(monkeypatch):
    rec = asyncio.run(
        _run("u1", [_p(store=MemoryStore.SEMANTIC, confidence=_MIN_ACCEPT_CONFIDENCE)], monkeypatch=monkeypatch)
    )
    assert len(rec.calls) == 1, "SEMANTIC at exactly the floor must pass through"


def test_episodic_bypasses_confidence_gate(monkeypatch):
    below_floor = _MIN_ACCEPT_CONFIDENCE - 0.01
    rec = asyncio.run(
        _run("u1", [_p(store=MemoryStore.EPISODIC, confidence=below_floor)], monkeypatch=monkeypatch)
    )
    assert len(rec.calls) == 1, (
        f"EPISODIC must persist regardless of confidence (got {below_floor}, floor is {_MIN_ACCEPT_CONFIDENCE})"
    )


# ---------------------------------------------------------------------------
# (d) Content validation: empty/whitespace skipped; over-long truncated
# ---------------------------------------------------------------------------


def test_whitespace_only_content_skipped(monkeypatch):
    rec = asyncio.run(_run("u1", [_p(content="   ")], monkeypatch=monkeypatch))
    assert not rec.calls, "whitespace-only content must be skipped (not persisted)"


def test_empty_content_skipped(monkeypatch):
    rec = asyncio.run(_run("u1", [_p(content="")], monkeypatch=monkeypatch))
    assert not rec.calls, "empty content must be skipped (not persisted)"


def test_over_long_content_truncated_to_max(monkeypatch):
    long_content = "x" * (_MAX_CONTENT_CHARS + 500)
    rec = asyncio.run(_run("u1", [_p(content=long_content)], monkeypatch=monkeypatch))
    assert len(rec.calls) == 1, "over-long content must still produce one upsert (truncated)"
    assert len(rec.calls[0]["content"]) == _MAX_CONTENT_CHARS, (
        f"content must be truncated to {_MAX_CONTENT_CHARS} chars, "
        f"got {len(rec.calls[0]['content'])}"
    )


# ---------------------------------------------------------------------------
# (e) Embedder down — drop quietly, no upsert, no raise
# ---------------------------------------------------------------------------


def test_embedder_down_drops_quietly_no_upsert(monkeypatch):
    rec = asyncio.run(
        _run("u1", [_p()], monkeypatch=monkeypatch, embed_fn=_embed_down())
    )
    assert not rec.calls, "embedder-down must produce no upsert (quiet drop)"
    # If an exception had been raised, asyncio.run would have propagated it here.


# ---------------------------------------------------------------------------
# (f) Dedup path
# ---------------------------------------------------------------------------


def test_dedup_hit_refreshes_existing_point_id(monkeypatch):
    """A search score at or above _DEDUP_SIMILARITY must reuse the existing point_id."""
    rec = asyncio.run(
        _run(
            "u1",
            [_p(confidence=0.7)],
            monkeypatch=monkeypatch,
            search_fn=_search_hit(score=_DEDUP_SIMILARITY, existing_id="old-pt", existing_conf=0.5),
        )
    )
    assert len(rec.calls) == 1
    assert rec.calls[0]["point_id"] == "old-pt", (
        "dedup hit must reuse the existing point_id (REFRESH, not INSERT)"
    )


def test_dedup_hit_takes_max_confidence(monkeypatch):
    """When existing confidence is higher, max wins."""
    rec_higher_existing = asyncio.run(
        _run(
            "u1",
            [_p(confidence=0.6)],
            monkeypatch=monkeypatch,
            search_fn=_search_hit(score=_DEDUP_SIMILARITY + 0.01, existing_id="pt", existing_conf=0.95),
        )
    )
    assert rec_higher_existing.calls[0]["confidence"] == 0.95, (
        "max(proposal=0.6, existing=0.95) must yield 0.95"
    )

    rec_higher_proposal = asyncio.run(
        _run(
            "u1",
            [_p(confidence=0.9)],
            monkeypatch=monkeypatch,
            search_fn=_search_hit(score=_DEDUP_SIMILARITY, existing_id="pt2", existing_conf=0.3),
        )
    )
    assert rec_higher_proposal.calls[0]["confidence"] == 0.9, (
        "max(proposal=0.9, existing=0.3) must yield 0.9"
    )


def test_dedup_miss_inserts_new_point(monkeypatch):
    """A score below _DEDUP_SIMILARITY must insert a new point (point_id=None)."""
    rec = asyncio.run(
        _run(
            "u1",
            [_p()],
            monkeypatch=monkeypatch,
            search_fn=_search_hit(score=_DEDUP_SIMILARITY - 0.01, existing_id="old-pt"),
        )
    )
    assert len(rec.calls) == 1
    assert rec.calls[0]["point_id"] is None, (
        "dissimilar hit (below dedup threshold) must NOT reuse point_id (new INSERT)"
    )


# ---------------------------------------------------------------------------
# (g) Fail-closed scope
# ---------------------------------------------------------------------------


def test_empty_string_user_id_fail_closed(monkeypatch):
    tripwire = _EmbedTripwire()
    monkeypatch.setattr(emb_mod, "embed", tripwire)
    rec = _Recorder()
    monkeypatch.setattr(store_mod, "upsert", rec)
    asyncio.run(MemoryManager().record_write_proposals("", "sess", [_p()]))
    assert not rec.calls, "empty user_id must return immediately (no embed, no upsert)"


def test_none_user_id_fail_closed(monkeypatch):
    tripwire = _EmbedTripwire()
    monkeypatch.setattr(emb_mod, "embed", tripwire)
    rec = _Recorder()
    monkeypatch.setattr(store_mod, "upsert", rec)
    asyncio.run(MemoryManager().record_write_proposals(None, "sess", [_p()]))  # type: ignore[arg-type]
    assert not rec.calls, "None user_id must return immediately (no embed, no upsert)"


def test_empty_proposals_list_fail_closed(monkeypatch):
    tripwire = _EmbedTripwire()
    monkeypatch.setattr(emb_mod, "embed", tripwire)
    rec = _Recorder()
    monkeypatch.setattr(store_mod, "upsert", rec)
    asyncio.run(MemoryManager().record_write_proposals("u1", "sess", []))
    assert not rec.calls, "empty proposals list must return immediately (no embed, no upsert)"


# ---------------------------------------------------------------------------
# (h) Upsert scoping: caller user_id, correct tier + _TIER_TRUST
# ---------------------------------------------------------------------------


def test_upsert_carries_caller_user_id(monkeypatch):
    rec = asyncio.run(
        _run(
            "tenant-abc",
            [
                _p(store=MemoryStore.EPISODIC),
                _p(store=MemoryStore.SEMANTIC, confidence=0.95),
                _p(store=MemoryStore.PROCEDURAL, confidence=0.95),
            ],
            monkeypatch=monkeypatch,
        )
    )
    assert len(rec.calls) == 3
    for call in rec.calls:
        assert call["user_id"] == "tenant-abc", (
            f"upsert for tier {call['tier']} must carry user_id='tenant-abc'"
        )


def test_upsert_carries_correct_tier_and_trust(monkeypatch):
    rec = asyncio.run(
        _run(
            "u1",
            [
                _p(store=MemoryStore.EPISODIC),
                _p(store=MemoryStore.SEMANTIC, confidence=0.95),
                _p(store=MemoryStore.PROCEDURAL, confidence=0.95),
            ],
            monkeypatch=monkeypatch,
        )
    )
    stored_tiers = {c["tier"] for c in rec.calls}
    assert MemoryStore.EPISODIC in stored_tiers
    assert MemoryStore.SEMANTIC in stored_tiers
    assert MemoryStore.PROCEDURAL in stored_tiers
    for call in rec.calls:
        expected_trust = _TIER_TRUST[call["tier"]]
        assert call["trust"] == expected_trust, (
            f"tier {call['tier']} must carry trust={expected_trust}, got {call['trust']}"
        )


# ---------------------------------------------------------------------------
# (i) Return contract — record_write_proposals returns ONLY what it persisted
# ---------------------------------------------------------------------------

async def _run_returning(
    user_id, proposals, *, monkeypatch, embed_fn=None, search_fn=None,
):
    rec = _Recorder()
    monkeypatch.setattr(emb_mod, "embed", embed_fn or _embed_ok())
    monkeypatch.setattr(store_mod, "search", search_fn or _search_miss())
    monkeypatch.setattr(store_mod, "upsert", rec)
    result = await MemoryManager().record_write_proposals(user_id, "sess-test", proposals)
    return rec, result


def test_returns_only_the_persisted_subset(monkeypatch):
    kept = _p(store=MemoryStore.EPISODIC, content="kept", confidence=0.9)
    dropped = _p(store=MemoryStore.SEMANTIC, content="dropped", confidence=_MIN_ACCEPT_CONFIDENCE - 0.01)
    rec, result = asyncio.run(_run_returning("u1", [kept, dropped], monkeypatch=monkeypatch))
    # the low-confidence semantic proposal is dropped; only the episodic write returns
    assert [p.content for p in result] == ["kept"]
    assert len(rec.calls) == 1


def test_returns_empty_when_embedder_down(monkeypatch):
    _, result = asyncio.run(_run_returning("u1", [_p()], monkeypatch=monkeypatch, embed_fn=_embed_down()))
    assert result == [], "embedder-down persists nothing and returns an empty list"


def test_returns_empty_on_missing_scope(monkeypatch):
    _, result = asyncio.run(_run_returning("", [_p()], monkeypatch=monkeypatch))
    assert result == []


def test_returns_empty_when_upsert_fails_midflight(monkeypatch):
    """store.upsert returning None (a live Qdrant fault mid-call, or a refused
    tenant-mismatched point) must NOT be reported as persisted — regression for the
    phantom-write bug where _persist_one discarded upsert's return value and always
    returned True regardless of what actually happened at the store."""
    def failing_upsert(*a, **k) -> None:
        return None

    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_miss())
    monkeypatch.setattr(store_mod, "upsert", failing_upsert)
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess-test", [_p()]))
    assert result == [], "a store.upsert failure must not be reported as a persisted write"


# ---------------------------------------------------------------------------
# (j) Write path is BOUNDED — a stalled store times out, drops the rest, no hang
# ---------------------------------------------------------------------------

def test_write_timeout_drops_remaining_writes(monkeypatch):
    from foundation import constants as fconst   # the exact module manager reads

    async def _hanging_embed(texts):
        await asyncio.sleep(5)   # far longer than the (patched) write deadline
        return [_DUMMY_VEC for _ in texts]

    monkeypatch.setattr(fconst, "MEMORY_WRITE_TIMEOUT_S", 0.05)
    rec, result = asyncio.run(
        _run_returning(
            "u1", [_p(content="a"), _p(content="b")],
            monkeypatch=monkeypatch, embed_fn=_hanging_embed,
        )
    )
    # a stalled store must not hang the delivered path: bounded, persists nothing
    assert result == []
    assert not rec.calls


# ---------------------------------------------------------------------------
# Policy summary table
# ---------------------------------------------------------------------------

_RULE_LABELS = [
    ("a", "WORKING tier never persisted",                      "SKIPPED"),
    ("b", "WIKI redirected to SEMANTIC + correct trust",       "REDIRECTED"),
    ("c", "SEM/PROC below floor dropped; EPISODIC always",     "SKIPPED/PERSISTED"),
    ("d", "Empty/whitespace skipped; over-long truncated",     "SKIPPED/TRUNCATED"),
    ("e", "Embedder down drops quietly, no raise",             "DROPPED"),
    ("f", "Dedup hit refreshes point_id; miss inserts new",    "DEDUP-REFRESHED"),
    ("g", "Fail-closed: empty user_id/proposals = no-op",      "FAIL-CLOSED"),
    ("h", "Upsert scoped to user_id + correct tier+trust",     "PERSISTED"),
]


def test_write_door_policy_table(monkeypatch):
    """
    Re-exercises every rule inline and prints a summary table.

    A real divergence from the documented policy is flagged as VIOLATED,
    written to ~/.clannon_proposal, and surfaced via pytest.fail so CI
    reports it as a gap — the curator routes it rather than the executor
    editing manager.py.
    """
    rows: list[tuple[str, str, str, str]] = []
    gaps: list[str] = []

    def check(rule: str, outcome: str, fn):
        try:
            fn()
            rows.append((rule, outcome, "policy held", ""))
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)[:80]
            rows.append((rule, outcome, "VIOLATED", detail))
            gaps.append(f"Rule ({rule}): {detail}")

    # --- (a) ---
    def _a():
        rec = asyncio.run(_run("u", [_p(store=MemoryStore.WORKING)], monkeypatch=monkeypatch))
        assert not rec.calls

    check("a", "SKIPPED", _a)

    # --- (b) ---
    def _b():
        rec = asyncio.run(
            _run(
                "u",
                [MemoryWriteProposal(store=MemoryStore.WIKI, content="fact", confidence=0.95)],
                monkeypatch=monkeypatch,
            )
        )
        assert len(rec.calls) == 1
        assert rec.calls[0]["tier"] is MemoryStore.SEMANTIC
        assert rec.calls[0]["trust"] == _TIER_TRUST[MemoryStore.SEMANTIC]

    check("b", "REDIRECTED", _b)

    # --- (c) ---
    def _c():
        low = _MIN_ACCEPT_CONFIDENCE - 0.01
        rec = asyncio.run(_run("u", [_p(store=MemoryStore.SEMANTIC, confidence=low)], monkeypatch=monkeypatch))
        assert not rec.calls, "semantic below floor not dropped"
        rec2 = asyncio.run(_run("u", [_p(store=MemoryStore.EPISODIC, confidence=low)], monkeypatch=monkeypatch))
        assert len(rec2.calls) == 1, "episodic not persisted without confidence gate"

    check("c", "SKIPPED/PERSISTED", _c)

    # --- (d) ---
    def _d():
        rec_ws = asyncio.run(_run("u", [_p(content="  ")], monkeypatch=monkeypatch))
        assert not rec_ws.calls, "whitespace not skipped"
        rec_long = asyncio.run(_run("u", [_p(content="x" * (_MAX_CONTENT_CHARS + 100))], monkeypatch=monkeypatch))
        assert len(rec_long.calls[0]["content"]) == _MAX_CONTENT_CHARS, "over-long not truncated"

    check("d", "SKIPPED/TRUNCATED", _d)

    # --- (e) ---
    def _e():
        rec = asyncio.run(_run("u", [_p()], monkeypatch=monkeypatch, embed_fn=_embed_down()))
        assert not rec.calls, "embedder-down still produced upsert"

    check("e", "DROPPED", _e)

    # --- (f) ---
    def _f():
        rec_hit = asyncio.run(
            _run(
                "u",
                [_p(confidence=0.7)],
                monkeypatch=monkeypatch,
                search_fn=_search_hit(_DEDUP_SIMILARITY, "old-id"),
            )
        )
        assert rec_hit.calls[0]["point_id"] == "old-id", "dedup hit did not refresh point_id"
        rec_miss = asyncio.run(
            _run(
                "u",
                [_p()],
                monkeypatch=monkeypatch,
                search_fn=_search_hit(_DEDUP_SIMILARITY - 0.01, "old-id"),
            )
        )
        assert rec_miss.calls[0]["point_id"] is None, "dissimilar hit reused point_id"

    check("f", "DEDUP-REFRESHED", _f)

    # --- (g) ---
    def _g():
        trip = _EmbedTripwire()
        monkeypatch.setattr(emb_mod, "embed", trip)
        rec_g = _Recorder()
        monkeypatch.setattr(store_mod, "upsert", rec_g)
        asyncio.run(MemoryManager().record_write_proposals("", "s", [_p()]))
        assert not rec_g.calls, "empty user_id produced upsert"
        asyncio.run(MemoryManager().record_write_proposals("u", "s", []))
        assert not rec_g.calls, "empty proposals produced upsert"

    check("g", "FAIL-CLOSED", _g)

    # --- (h) ---
    def _h():
        rec = asyncio.run(_run("tenant-xyz", [_p(store=MemoryStore.EPISODIC)], monkeypatch=monkeypatch))
        assert rec.calls[0]["user_id"] == "tenant-xyz", "upsert carries wrong user_id"
        assert rec.calls[0]["trust"] == _TIER_TRUST[MemoryStore.EPISODIC], "upsert carries wrong trust"

    check("h", "PERSISTED", _h)

    # Print table
    w_rule, w_policy, w_outcome, w_verdict = 4, 44, 22, 14
    sep = (
        "+"
        + "+".join("-" * (w + 2) for w in (w_rule, w_policy, w_outcome, w_verdict))
        + "+"
    )
    fmt = "| {{:{w_rule}}} | {{:{w_policy}}} | {{:{w_outcome}}} | {{:{w_verdict}}} |".format(
        w_rule=w_rule, w_policy=w_policy, w_outcome=w_outcome, w_verdict=w_verdict
    )
    print("\n\n  Write-door persistence policy (manager.py:225-267)")
    print(sep)
    print(fmt.format("Rule", "Policy", "Outcome class", "Verdict"))
    print(sep)
    for i, (rule, policy, outcome) in enumerate(_RULE_LABELS):
        _, _, verdict, _ = rows[i]
        print(fmt.format(rule, policy, outcome, verdict))
    print(sep)

    if gaps:
        note = "\n".join(f"  - {g}" for g in gaps)
        message = (
            "\n## Write-door policy gaps found by test/memory-write-door-policy\n\n"
            f"{note}\n"
            "\nThese are REAL divergences from the documented policy. "
            "Do NOT edit manager.py without curator/maintainer review.\n"
        )
        try:
            with open("/home/amrit/.clannon_proposal", "a") as fh:
                fh.write(message)
        except OSError:
            pass
        pytest.fail(
            "Write-door policy VIOLATED — see table above and ~/.clannon_proposal:\n"
            + "\n".join(gaps)
        )
