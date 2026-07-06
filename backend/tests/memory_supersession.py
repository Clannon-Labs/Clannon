"""
EB1 — knowledge evolution / temporal truth: supersession detection.

Ratified design (Option B): an LLM judge decides whether a newly-written memory
supersedes an existing one it's closely related to (not merely similar — a later,
updated version of the SAME specific fact/preference). FAIL-CLOSED throughout: any
doubt, malformed output, or fault leaves history untouched. A superseded item stays
retrievable (temporal truth, not erasure).

Four layers, each hermetic (no live Qdrant, no network, no paid keys):
  1. store.mark_superseded  — the targeted payload patch + its existence/ownership
     refusal (stricter than _owns_point's insert-friendly "doesn't exist -> True").
  2. writer.judge_supersession — the LLM call's own fail-closed contract (stubbed
     build_agent/run_structured, mirroring security/filter's seam-testing convention).
  3. manager._persist_one / _maybe_mark_superseded — the orchestration: which hits
     are even candidates (band + tier + fresh-insert gating), and that a judge/mark
     fault or timeout never breaks the write it's attached to.
  4. End-to-end: hydrate() already surfaces a marked item without any read-path
     change (CB1 already propagates superseded_by; nothing filters on it) — proven
     here by actually driving a write -> mark -> read round trip, not just read.

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_supersession.py -v
"""
from __future__ import annotations

import asyncio
import sys
import time

import core.memory.embeddings as emb_mod
import core.memory.store as store_mod
import core.memory.writer as writer_mod
from core.memory import store
from core.memory.manager import MemoryManager, _DEDUP_SIMILARITY, _SUPERSESSION_FLOOR
from foundation import HydrationRequest, MemoryKind, MemoryStore, MemoryWriteProposal, NormalizedInput

# NOT `import core.memory.manager as manager_mod`: core/memory/__init__.py does
# `from .manager import MemoryManager, manager`, which shadows the `manager`
# submodule attribute on the `core.memory` package with the singleton instance —
# so `import core.memory.manager as x` / `from core.memory import manager as x`
# both silently bind x to the MemoryManager() instance, not the module. Going
# through sys.modules (already populated by the `from ... import` above) gets the
# real module so monkeypatching its attributes actually affects what the manager's
# own code reads at runtime.
manager_mod = sys.modules["core.memory.manager"]

_MID_BAND = (_SUPERSESSION_FLOOR + _DEDUP_SIMILARITY) / 2  # comfortably inside [floor, dedup)


# ---------------------------------------------------------------------------
# 1. store.mark_superseded — real logic, fake Qdrant client (mirrors
#    memory_typed_knowledge.py's _FakeClient convention)
# ---------------------------------------------------------------------------

class _FakePoint:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


class _FakeClient:
    def __init__(self, points: dict[str, dict]) -> None:
        self._points = points
        self.set_payload_calls: list[dict] = []

    def retrieve(self, collection, ids, with_payload=None):
        pid = ids[0]
        if pid not in self._points:
            return []
        return [_FakePoint(self._points[pid])]

    def set_payload(self, collection, payload, points):
        self.set_payload_calls.append(dict(collection=collection, payload=payload, points=points))


def test_mark_superseded_patches_existing_owned_point(monkeypatch):
    client = _FakeClient({"old-id": {"user_id": "u1"}})
    monkeypatch.setattr(store, "_qdrant", lambda: client)
    ok = store.mark_superseded(MemoryStore.SEMANTIC, "u1", "old-id", "new-id")
    assert ok is True
    assert client.set_payload_calls == [dict(
        collection=store.COLLECTIONS[MemoryStore.SEMANTIC],
        payload={"superseded_by": "new-id"},
        points=["old-id"],
    )]


def test_mark_superseded_refuses_nonexistent_point(monkeypatch):
    client = _FakeClient({})
    monkeypatch.setattr(store, "_qdrant", lambda: client)
    ok = store.mark_superseded(MemoryStore.SEMANTIC, "u1", "ghost-id", "new-id")
    assert ok is False, "marking a point that doesn't exist must not silently succeed"
    assert not client.set_payload_calls


def test_mark_superseded_refuses_foreign_owned_point(monkeypatch):
    client = _FakeClient({"old-id": {"user_id": "someone-else"}})
    monkeypatch.setattr(store, "_qdrant", lambda: client)
    ok = store.mark_superseded(MemoryStore.SEMANTIC, "u1", "old-id", "new-id")
    assert ok is False, "must refuse to patch another user's point"
    assert not client.set_payload_calls


def test_mark_superseded_false_when_store_down(monkeypatch):
    monkeypatch.setattr(store, "_qdrant", lambda: None)
    assert store.mark_superseded(MemoryStore.SEMANTIC, "u1", "old-id", "new-id") is False


def test_mark_superseded_false_on_missing_scope(monkeypatch):
    client = _FakeClient({"old-id": {"user_id": "u1"}})
    monkeypatch.setattr(store, "_qdrant", lambda: client)
    assert store.mark_superseded(MemoryStore.SEMANTIC, "", "old-id", "new-id") is False
    assert store.mark_superseded(MemoryStore.SEMANTIC, "u1", "", "new-id") is False
    assert not client.set_payload_calls


def test_mark_superseded_false_on_client_fault(monkeypatch):
    class _FaultyClient:
        def retrieve(self, *a, **k):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(store, "_qdrant", lambda: _FaultyClient())
    assert store.mark_superseded(MemoryStore.SEMANTIC, "u1", "old-id", "new-id") is False


# ---------------------------------------------------------------------------
# 2. writer.judge_supersession — fail-closed LLM contract (build_agent /
#    run_structured stubbed, same seam-testing convention as output_filter_grounding.py)
# ---------------------------------------------------------------------------

def _stub_agent(monkeypatch, verdict=None, raises: Exception | None = None):
    monkeypatch.setattr(writer_mod, "build_agent", lambda *a, **kw: object())
    captured: dict = {}

    async def fake_run_structured(handle, prompt, **kw):
        captured["prompt"] = prompt
        if raises is not None:
            raise raises
        return verdict

    monkeypatch.setattr(writer_mod, "run_structured", fake_run_structured)
    return captured


def test_judge_supersession_true_when_confident_and_supersedes(monkeypatch):
    captured = _stub_agent(
        monkeypatch,
        verdict=writer_mod._SupersessionVerdict(supersedes=True, confident=True, rationale="value changed"),
    )
    result = asyncio.run(writer_mod.judge_supersession("user prefers metric units now", "user prefers imperial units"))
    assert result is True
    assert "user prefers metric units now" in captured["prompt"]
    assert "user prefers imperial units" in captured["prompt"]


def test_judge_supersession_false_when_not_confident(monkeypatch):
    _stub_agent(monkeypatch, verdict=writer_mod._SupersessionVerdict(supersedes=True, confident=False))
    result = asyncio.run(writer_mod.judge_supersession("new", "existing"))
    assert result is False, "supersedes=True but NOT confident must still fail closed"


def test_judge_supersession_false_when_not_supersedes(monkeypatch):
    _stub_agent(monkeypatch, verdict=writer_mod._SupersessionVerdict(supersedes=False, confident=True))
    assert asyncio.run(writer_mod.judge_supersession("new", "existing")) is False


def test_judge_supersession_false_on_model_fault(monkeypatch):
    _stub_agent(monkeypatch, raises=RuntimeError("model unavailable"))
    assert asyncio.run(writer_mod.judge_supersession("new", "existing")) is False


# ---------------------------------------------------------------------------
# 3. manager orchestration — candidate gating (band + tier + fresh-insert) and
#    best-effort isolation (judge/mark fault or timeout never breaks the write)
# ---------------------------------------------------------------------------

_DUMMY_VEC: list[float] = [0.1] * 768


def _embed_ok():
    async def embed(texts: list[str]) -> list[list[float]]:
        return [_DUMMY_VEC for _ in texts]
    return embed


def _search_hit(score: float, existing_id: str = "existing-id", content: str = "old fact"):
    def search(tier, user_id, vector, limit) -> list[dict]:
        return [{"id": existing_id, "score": score, "content": content, "confidence": 0.5}]
    return search


def _p(store=MemoryStore.SEMANTIC, content: str = "new fact", confidence: float = 0.9) -> MemoryWriteProposal:
    return MemoryWriteProposal(store=store, content=content, confidence=confidence)


def _tripwire():
    async def fail(*a, **k):
        raise AssertionError("must not be called for this case")
    return fail


def test_in_band_hit_confident_judge_marks_superseded(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    marks: list[tuple] = []
    monkeypatch.setattr(
        store_mod, "mark_superseded",
        lambda tier, user_id, point_id, superseded_by: marks.append((tier, user_id, point_id, superseded_by)) or True,
    )

    async def fake_judge(new_content, existing_content):
        return True

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    assert len(result) == 1, "the new write must still be reported as persisted"
    assert marks == [(MemoryStore.SEMANTIC, "u1", "existing-id", "new-id")]


def test_judge_not_called_below_supersession_floor(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_SUPERSESSION_FLOOR - 0.05))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")
    monkeypatch.setattr(writer_mod, "judge_supersession", _tripwire())
    monkeypatch.setattr(store_mod, "mark_superseded", _tripwire())

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    assert len(result) == 1


def test_judge_not_called_for_episodic_tier(monkeypatch):
    """An ORDINARY (non-DECISION) EPISODIC proposal is turn history, each its own
    point in time — not a candidate. A DECISION in EPISODIC is a different case,
    covered by test_decision_in_episodic_tier_is_also_eligible below (CB4 settled
    DECISION as EPISODIC; the exclusion here must not blanket-exclude the tier)."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")
    monkeypatch.setattr(writer_mod, "judge_supersession", _tripwire())

    result = asyncio.run(MemoryManager().record_write_proposals(
        "u1", "sess", [_p(store=MemoryStore.EPISODIC)]
    ))
    assert len(result) == 1


def test_decision_in_episodic_tier_is_also_eligible(monkeypatch):
    """CB4 settled MemoryKind.DECISION's tier as EPISODIC (matching c4_decision_
    memory.py + orchestration's ratified runtime bridge). A DECISION is supersedable
    regardless of which tier it lives in — the append-only dedup exemption was
    already tier-agnostic, but the separate judge-invocation gate was not, and would
    have silently never formed a link for an EPISODIC decision. Regression for that
    gap."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    marks: list[tuple] = []
    monkeypatch.setattr(
        store_mod, "mark_superseded",
        lambda tier, user_id, point_id, superseded_by: marks.append((tier, point_id, superseded_by)) or True,
    )

    async def fake_judge(new_content, existing_content):
        return True

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)
    proposal = MemoryWriteProposal(
        store=MemoryStore.EPISODIC, content="revised decision", confidence=0.9,
        kind=MemoryKind.DECISION,
    )
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [proposal]))
    assert len(result) == 1
    assert marks, (
        "a DECISION-kind proposal in the EPISODIC tier must still form a "
        "supersession link — the judge-invocation gate must not exclude it"
    )
    assert marks[0][0] == MemoryStore.EPISODIC


def test_decision_call_site_requires_decision_kind_not_any_kind(monkeypatch):
    """The eligibility widening is specifically kind == DECISION, not "any kind in
    EPISODIC" — an EPISODIC proposal with an unrelated/legacy kind value must still
    be excluded, same as test_judge_not_called_for_episodic_tier."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")
    monkeypatch.setattr(writer_mod, "judge_supersession", _tripwire())

    proposal = MemoryWriteProposal(
        store=MemoryStore.EPISODIC, content="new fact", confidence=0.9, kind=MemoryKind.FACT,
    )
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [proposal]))
    assert len(result) == 1


def test_judge_not_called_on_dedup_merge(monkeypatch):
    """score >= _DEDUP_SIMILARITY takes the merge path (same fact restated), not a
    supersession candidate (a different, competing fact)."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_DEDUP_SIMILARITY))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "existing-id")
    monkeypatch.setattr(writer_mod, "judge_supersession", _tripwire())

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    assert len(result) == 1


def test_procedural_tier_is_also_eligible(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    marks: list[tuple] = []
    monkeypatch.setattr(
        store_mod, "mark_superseded",
        lambda tier, user_id, point_id, superseded_by: marks.append((tier, point_id, superseded_by)) or True,
    )

    async def fake_judge(new_content, existing_content):
        return True

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)
    result = asyncio.run(MemoryManager().record_write_proposals(
        "u1", "sess", [_p(store=MemoryStore.PROCEDURAL)]
    ))
    assert len(result) == 1
    assert marks == [(MemoryStore.PROCEDURAL, "existing-id", "new-id")]


def test_low_confidence_judge_does_not_mark(monkeypatch):
    """writer.judge_supersession already fails closed internally; this proves the
    manager honours a False verdict (no mark) rather than assuming true."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    async def fake_judge(new_content, existing_content):
        return False

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)
    marks: list = []
    monkeypatch.setattr(store_mod, "mark_superseded", lambda *a, **k: marks.append(a) or True)

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    assert len(result) == 1
    assert marks == []


def test_judge_fault_does_not_break_the_write(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    async def boom(new_content, existing_content):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(writer_mod, "judge_supersession", boom)
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    assert len(result) == 1, "a judge fault must not drop the already-successful write"


def test_mark_failure_does_not_break_the_write(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    async def fake_judge(new_content, existing_content):
        return True

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)
    monkeypatch.setattr(store_mod, "mark_superseded", lambda *a, **k: False)  # store refuses

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    assert len(result) == 1, "a mark refusal must not break the write it's attached to"


def test_judge_timeout_is_bounded_independently(monkeypatch):
    """A slow/hanging judge must be cut off well inside
    settings.MEMORY.write_timeout_s, and must never cause
    record_write_proposals to mistake the already-successful upsert for a
    stalled store (which would incorrectly drop this AND all later writes)."""
    monkeypatch.setattr(manager_mod, "_SUPERSESSION_TIMEOUT_S", 0.05)
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(score=_MID_BAND))
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")

    async def slow_judge(new_content, existing_content):
        await asyncio.sleep(1.0)  # far longer than the patched timeout
        return True

    monkeypatch.setattr(writer_mod, "judge_supersession", slow_judge)

    started = time.monotonic()
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p()]))
    elapsed = time.monotonic() - started
    assert len(result) == 1, "a slow judge must not cause the outer write-timeout to drop the write"
    assert elapsed < 1.0, "the inner timeout must cut the judge off well before its own sleep finishes"


# ---------------------------------------------------------------------------
# 4. End-to-end: write -> mark -> read. Proves hydrate() genuinely keeps a
#    superseded item SURFACED (temporal truth, not erasure) by actually driving
#    the round trip, not by inspecting hydrate()'s source for the absence of a filter.
# ---------------------------------------------------------------------------

class _E2EStore:
    """In-memory double covering search/upsert/mark_superseded/is_down together,
    so a write's dedup-probe search and hydrate()'s broader search share one
    backing list — a real round trip, not two disconnected doubles."""

    def __init__(self, candidate_score: float) -> None:
        self._rows: list[dict] = []
        self._candidate_score = candidate_score

    def search(self, tier, user_id, vector, limit: int = 8) -> list[dict]:
        rows = [{**r, "score": self._candidate_score if limit == 1 else 1.0}
                for r in self._rows if r["user_id"] == user_id]
        return rows[-limit:] if limit == 1 else rows[:limit]

    def upsert(self, tier, user_id, session_id, trace_id, vector, content,
               rationale, confidence, trust, point_id=None, *,
               kind="unspecified", valid_at=0.0, source="", superseded_by="", participants="") -> str:
        pid = point_id or f"pt-{len(self._rows) + 1}"
        row = dict(
            id=pid, user_id=user_id, session_id=session_id, trace_id=trace_id,
            content=content, rationale=rationale, confidence=confidence, trust=trust,
            created_at=1_000.0, kind=kind, valid_at=valid_at, source=source,
            superseded_by=superseded_by, participants=participants,
        )
        if point_id is not None:
            for r in self._rows:
                if r["id"] == point_id and r["user_id"] == user_id:
                    r.update(row)
                    return point_id
        self._rows.append(row)
        return pid

    def mark_superseded(self, tier, user_id, point_id, superseded_by) -> bool:
        for r in self._rows:
            if r["id"] == point_id and r["user_id"] == user_id:
                r["superseded_by"] = superseded_by
                return True
        return False

    def is_down(self) -> bool:
        return False


def test_superseded_item_stays_surfaced_on_retrieval(monkeypatch):
    double = _E2EStore(candidate_score=_MID_BAND)
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", double.search)
    monkeypatch.setattr(store_mod, "upsert", double.upsert)
    monkeypatch.setattr(store_mod, "mark_superseded", double.mark_superseded)
    monkeypatch.setattr(store_mod, "is_down", double.is_down)

    async def fake_judge(new_content, existing_content):
        return True  # confident supersession, per the ratified fail-closed design

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)

    mgr = MemoryManager()
    old = asyncio.run(mgr.record_write_proposals(
        "u1", "sess", [_p(content="Client Meridian's ARR is $6M")]
    ))
    new = asyncio.run(mgr.record_write_proposals(
        "u1", "sess", [_p(content="Client Meridian's ARR is now $9M")]
    ))
    assert len(old) == 1 and len(new) == 1, "both writes must be reported as persisted"

    package = asyncio.run(mgr.hydrate(HydrationRequest(
        session_id="sess", user_id="u1",
        normalized=NormalizedInput(modality="text", content_type="text/plain", content="Meridian ARR"),
    )))
    contents = {i.content: i for i in package.items}
    assert len(contents) == 2, "the superseded memory must stay retrievable, not be filtered out"
    old_item = contents["Client Meridian's ARR is $6M"]
    new_item = contents["Client Meridian's ARR is now $9M"]
    assert old_item.superseded_by, "the old item must carry a visible superseded_by link"
    assert old_item.superseded_by == double._rows[1]["id"], "must point at the memory that replaced it"
    assert new_item.superseded_by == "", "the current item is not itself superseded"


# ---------------------------------------------------------------------------
# 5. CB4 — MemoryKind.DECISION is append-only: the keystone guarantee. A
#    near-identical revision at or above _DEDUP_SIMILARITY must NEVER take the
#    silent merge-overwrite path (which replaces content/rationale with no
#    trace — CB4's own "reasoning is lost" fail condition). It must always
#    insert fresh and go through the EB1 supersession judge instead.
# ---------------------------------------------------------------------------

def test_decision_at_dedup_similarity_never_merges(monkeypatch):
    """A DECISION proposal scoring >= _DEDUP_SIMILARITY against an existing point
    must still insert FRESH (point_id=None), never reuse the existing point_id —
    the exact band a merge would otherwise silently overwrite in."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(
        score=_DEDUP_SIMILARITY, existing_id="decision-v1", content="We chose Option B: graph-first retrieval."
    ))

    upserts = []

    def fake_upsert(tier, *, user_id, session_id, trace_id, vector, content, rationale,
                     confidence, trust, point_id=None, kind="unspecified", valid_at=0.0,
                     source="", superseded_by="", participants=""):
        upserts.append(dict(content=content, point_id=point_id, kind=kind))
        return "decision-v2"

    monkeypatch.setattr(store_mod, "upsert", fake_upsert)

    async def fake_judge(new_content, existing_content):
        return True

    monkeypatch.setattr(writer_mod, "judge_supersession", fake_judge)
    monkeypatch.setattr(store_mod, "mark_superseded", lambda *a, **k: True)

    proposal = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC, kind=MemoryKind.DECISION, confidence=0.9,
        content="We chose Option B: graph-first retrieval, revised scope.",
        rationale="performance benchmarks favored graph traversal",
    )
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [proposal]))

    assert len(result) == 1, "the revision must still be reported as persisted"
    assert len(upserts) == 1, "exactly one upsert call — the original point is never touched"
    assert upserts[0]["point_id"] is None, "a DECISION must never merge — always a fresh insert"
    assert upserts[0]["kind"] == "decision"


def test_existing_decision_protected_from_a_different_kind_merge(monkeypatch):
    """An EXISTING decision must not be merge-overwritten either, even by an
    ordinary (non-DECISION) proposal that happens to score >= _DEDUP_SIMILARITY
    against it — append-only protects the existing record regardless of what
    kind the new, competing write claims to be."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _search_hit(
        score=_DEDUP_SIMILARITY, existing_id="decision-v1", content="We chose Option B."
    ))

    upserts = []

    def fake_upsert(tier, *, user_id, session_id, trace_id, vector, content, rationale,
                     confidence, trust, point_id=None, kind="unspecified", valid_at=0.0,
                     source="", superseded_by="", participants=""):
        upserts.append(dict(point_id=point_id))
        return "fact-1"

    monkeypatch.setattr(store_mod, "upsert", fake_upsert)
    # existing[0] carries kind="decision" in its payload — the FakeSearch helper
    # below doesn't set it, so patch search directly for this one case.
    def search_with_decision_kind(tier, user_id, vector, limit):
        return [{"id": "decision-v1", "score": _DEDUP_SIMILARITY, "content": "We chose Option B.",
                  "kind": "decision", "confidence": 0.9}]
    monkeypatch.setattr(store_mod, "search", search_with_decision_kind)

    proposal = _p(content="We chose Option B, restated.", confidence=0.9)  # ordinary FACT/default kind
    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [proposal]))

    assert len(result) == 1
    assert upserts[0]["point_id"] is None, (
        "an existing DECISION must never be merged into, even by a non-DECISION proposal"
    )


def test_kind_rank_has_decision_ranked_with_fact():
    from core.memory.manager import _KIND_RANK
    assert _KIND_RANK[MemoryKind.DECISION] == _KIND_RANK[MemoryKind.FACT]
