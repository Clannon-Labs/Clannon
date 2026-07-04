"""The /memory view must reflect only PERSISTED memory.

The memory-write timing fix persists a turn's memory ONLY on the delivered path, so on a
blocked / failed turn nothing is written. run_driver must match that: it surfaces
run.memory_writes ONLY for a delivered turn. A blocked turn whose ctx still carries an
in-flight proposal (e.g. a remember() the orchestrator made before the output filter
blocked the draft) must surface ZERO phantom memories — never a memory the user did not
actually get.

Hermetic: pipeline.run is faked (no models), and the DB-touching helpers are patched, so
this exercises run_driver.execute's outcome handling directly.
"""

import asyncio
from types import SimpleNamespace

from foundation import MemoryStore, MemoryWriteProposal
from api.run_state import RunState
import api.run_driver as rd


def _fake_flow(*, blocked=False, failed=False, proposed=(), persisted=()):
    """A finished Flow as run_driver sees it: only the fields execute() reads.

    `proposed` = what the orchestrator flagged (ctx.memory_writes_requested);
    `persisted` = what the Manager actually wrote (ctx.memory_writes_persisted).
    The /memory view surfaces ONLY the persisted set — the split is the point."""
    ctx = SimpleNamespace(
        blocked=blocked,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=blocked,            # a filter block is the case the timing fix guards
        failed=failed,
        failure_error=None,
        orchestrator_response=SimpleNamespace(text="the draft answer", message=""),
        final_response="the draft answer",
        memory_writes_requested=list(proposed),
        memory_writes_persisted=list(persisted),
        expert_findings=[],
        expert_calls=[],
    )
    return SimpleNamespace(ctx=ctx)


def _drive(monkeypatch, flow) -> RunState:
    """Run execute() against a faked pipeline + patched DB helpers, return the RunState."""
    async def fake_run(*a, **k):
        return flow
    monkeypatch.setattr(rd.pipeline, "run", fake_run)
    monkeypatch.setattr(rd, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(rd.STORE, "session_turns", lambda *a, **k: [])
    monkeypatch.setattr(rd.STORE, "persist", lambda run: None)

    run = RunState(id="r1", user_id="u", title="t", brief="b", session_id="r1")
    asyncio.run(rd.execute(run))
    return run


def test_blocked_turn_surfaces_zero_phantom_memories(monkeypatch):
    # the orchestrator proposed a remember() before the filter blocked the draft; it was
    # NOT persisted (timing fix), so it must not appear in the /memory view
    phantom = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC, content="a fact the user never actually got", confidence=0.95,
    )
    # proposed but never persisted (the turn blocked before persist_turn_memory ran)
    run = _drive(monkeypatch, _fake_flow(blocked=True, proposed=[phantom]))

    assert run.status == "blocked"
    assert run.block_stage == "filter"
    assert run.memory_writes == []          # zero phantom memories surfaced


def test_failed_turn_surfaces_zero_memories(monkeypatch):
    leftover = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC, content="unpersisted on a failed turn", confidence=0.95,
    )
    run = _drive(monkeypatch, _fake_flow(failed=True, proposed=[leftover]))

    assert run.status == "failed"
    assert run.memory_writes == []


def test_delivered_turn_still_surfaces_its_memory_writes(monkeypatch):
    # the contrast case: a delivered turn DID persist, so its writes show in the view
    written = MemoryWriteProposal(
        store=MemoryStore.EPISODIC, content="a real delivered memory", confidence=0.8,
    )
    run = _drive(monkeypatch, _fake_flow(proposed=[written], persisted=[written]))

    assert run.status == "delivered"
    assert [w["content"] for w in run.memory_writes] == ["a real delivered memory"]


def test_delivered_turn_surfaces_only_what_persisted_not_the_proposals(monkeypatch):
    # honesty: on a delivered turn the Manager may drop a proposal (low confidence /
    # dedup / store down). Only the PERSISTED subset surfaces — never the dropped one.
    written = MemoryWriteProposal(
        store=MemoryStore.EPISODIC, content="the memory that landed", confidence=0.9,
    )
    dropped = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC, content="proposed but rejected by the write policy", confidence=0.1,
    )
    run = _drive(monkeypatch, _fake_flow(proposed=[written, dropped], persisted=[written]))

    assert run.status == "delivered"
    assert [w["content"] for w in run.memory_writes] == ["the memory that landed"]
