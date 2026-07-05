"""Memory-write TIMING invariant.

A turn's episodic memory (and the background `learn()` distillation) is persisted ONLY
after the output filter ACCEPTS the draft and it is delivered — never for a draft the
filter blocks. The fix moved the write out of the orchestrator stage (which fired
PRE-filter) to a post-filter site in `core.pipeline`. These tests prove the
"rejected drafts never touch memory" invariant now holds on the INITIAL pass, not just
inside the bounded revision loop.

Unit tests exercise `orchestrator.persist_turn_memory` directly; the pipeline tests
drive `pipeline.run` with a fake orchestrator/filter/delivery trio so a blocked vs.
delivered draft can be compared end to end without Qdrant or an LLM.
"""

import asyncio
from types import SimpleNamespace

from foundation import (
    MemoryKind,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
    OrchestratorResponse,
    ToolCallRecord,
    VrakshaContext,
)
import core.pipeline as pipeline
from core.pipeline import Stage
from core.orchestrator import orchestrator as stage
from core.orchestrator.schemas import DecisionLogEntry


# >200 chars so a turn with this answer counts as SUBSTANTIVE (worth recording)
_SUBSTANTIVE_ANSWER = "Here is a thorough, real answer to the user's question. " * 6
_REAL_TASK = "Tell me everything about the project roadmap and the milestones we hit."


class _Recorder:
    """A stand-in MemoryPort that records exactly what got persisted (and when)."""

    def __init__(self):
        self.proposals: list = []
        self.record_calls = 0
        self.learned = 0
        self.last_user_id = None

    async def record_write_proposals(self, user_id, session_id, proposals):
        self.record_calls += 1
        self.last_user_id = user_id
        self.proposals.extend(proposals)

    async def learn(self, user_id, session_id, *, task, answer, findings):
        self.learned += 1


def _patch_memory(monkeypatch):
    """Route persist_turn_memory's writes to a Recorder and capture learn() scheduling
    deterministically (the spawned distillation coro is collected, never left dangling)."""
    rec = _Recorder()
    monkeypatch.setattr(stage, "build_default_ports", lambda ctx: SimpleNamespace(memory=rec))
    spawned: list = []
    monkeypatch.setattr(stage, "_spawn_background", lambda coro: spawned.append(coro))
    return rec, spawned


def _close(spawned):
    # we asserted whether distillation was SCHEDULED; don't actually run it
    for coro in spawned:
        coro.close()


def _ctx(task: str, answer: str) -> VrakshaContext:
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    ctx.normalized_input = NormalizedInput(modality="text", content_type="text/plain", content=task)
    ctx.orchestrator_response = OrchestratorResponse(text=answer, confidence=0.8)
    return ctx


# --------------------------------------------------------------------------- #
# Unit: persist_turn_memory in isolation
# --------------------------------------------------------------------------- #

def test_persist_writes_episodic_once_on_substantive_turn(monkeypatch):
    rec, spawned = _patch_memory(monkeypatch)
    ctx = _ctx(_REAL_TASK, _SUBSTANTIVE_ANSWER)

    asyncio.run(stage.persist_turn_memory(ctx))

    assert rec.record_calls == 1
    assert len(rec.proposals) == 1
    assert rec.proposals[0].store == MemoryStore.EPISODIC
    assert _SUBSTANTIVE_ANSWER[:30] in rec.proposals[0].content   # built from the delivered answer
    assert len(spawned) == 1                                      # learn() distillation scheduled
    _close(spawned)


def test_persist_skips_decision_proposal_for_a_tool_free_turn(monkeypatch):
    """CB4 runtime bridge, flood-prevention case: a substantive turn with an
    answer-kind decision-log entry but NO expert/tool participants gets its
    usual EPISODIC note -- and nothing else. A long, tool-free answer isn't an
    institutional decision; it has no "who was involved" to remember, and the
    episodic note already covers its content."""
    rec, spawned = _patch_memory(monkeypatch)
    ctx = _ctx(_REAL_TASK, _SUBSTANTIVE_ANSWER)
    ctx.decision_log.append(DecisionLogEntry(kind="answer", message=_SUBSTANTIVE_ANSWER))

    asyncio.run(stage.persist_turn_memory(ctx))

    assert rec.record_calls == 1
    assert len(rec.proposals) == 1                       # EPISODIC only, no DECISION
    assert rec.proposals[0].store == MemoryStore.EPISODIC
    assert rec.proposals[0].kind != MemoryKind.DECISION
    _close(spawned)


def test_persist_writes_a_decision_proposal_when_participants_are_real(monkeypatch):
    """CB4 runtime bridge, capture case: a substantive turn whose answer-decision
    had a real participant (a tool ran) gets BOTH the usual EPISODIC note AND
    exactly one DECISION proposal, with non-empty content/participants."""
    rec, spawned = _patch_memory(monkeypatch)
    ctx = _ctx(_REAL_TASK, _SUBSTANTIVE_ANSWER)
    ctx.tool_calls.append(ToolCallRecord(tool_name="search.web", arguments={}, success=True))
    ctx.decision_log.append(DecisionLogEntry(kind="answer", message=_SUBSTANTIVE_ANSWER))

    asyncio.run(stage.persist_turn_memory(ctx))

    assert rec.record_calls == 1
    assert len(rec.proposals) == 2                        # EPISODIC + exactly one DECISION
    decisions = [p for p in rec.proposals if p.kind == MemoryKind.DECISION]
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.store == MemoryStore.EPISODIC
    assert decision.content == _SUBSTANTIVE_ANSWER[:500]
    assert decision.participants == "search.web"
    _close(spawned)


def test_persist_skips_a_trivial_turn(monkeypatch):
    rec, spawned = _patch_memory(monkeypatch)
    ctx = _ctx("hi", "hello")            # short task + short answer, no findings => not substantive

    asyncio.run(stage.persist_turn_memory(ctx))

    assert rec.record_calls == 0         # nothing proposed, nothing recorded
    assert rec.proposals == []
    assert spawned == []                 # no distillation on a trivial turn


def test_persist_still_writes_remember_proposals(monkeypatch):
    # even a trivial turn persists an EXPLICIT remember() write the model chose to keep
    rec, spawned = _patch_memory(monkeypatch)
    ctx = _ctx("hi", "hello")
    ctx.memory_writes_requested.append(
        MemoryWriteProposal(store=MemoryStore.SEMANTIC, content="user prefers metric units", confidence=0.9)
    )

    asyncio.run(stage.persist_turn_memory(ctx))

    assert rec.record_calls == 1
    assert any(p.content == "user prefers metric units" for p in rec.proposals)
    assert spawned == []                 # trivial turn => no distillation, but the explicit write still lands
    _close(spawned)


def test_memory_fault_never_fails_persist(monkeypatch):
    # the write now happens post-filter; a fault there must be swallowed, never raised
    class Broken:
        async def record_write_proposals(self, *a, **k):
            raise RuntimeError("qdrant exploded")

    monkeypatch.setattr(stage, "build_default_ports", lambda ctx: SimpleNamespace(memory=Broken()))
    monkeypatch.setattr(stage, "_spawn_background", lambda coro: coro.close())
    ctx = _ctx(_REAL_TASK, _SUBSTANTIVE_ANSWER)

    asyncio.run(stage.persist_turn_memory(ctx))           # must NOT raise
    assert ctx.orchestrator_response.text == _SUBSTANTIVE_ANSWER


def test_persist_noops_without_a_response(monkeypatch):
    rec, spawned = _patch_memory(monkeypatch)
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")  # no orchestrator_response

    asyncio.run(stage.persist_turn_memory(ctx))

    assert rec.record_calls == 0
    assert spawned == []


# --------------------------------------------------------------------------- #
# Pipeline: the end-to-end timing invariant (blocked vs delivered)
# --------------------------------------------------------------------------- #

def _custom_stages(filter_fn):
    """A minimal orchestrator -> filter -> delivery pipeline. The orchestrator fake sets
    a SUBSTANTIVE draft + normalized_input (no normalizer in this subset); delivery sets
    the final response. `filter_fn` decides block vs pass per test."""
    async def fake_orch(flow):
        flow.ctx.normalized_input = NormalizedInput(
            modality="text", content_type="text/plain", content=_REAL_TASK,
        )
        flow.ctx.orchestrator_response = OrchestratorResponse(text=_SUBSTANTIVE_ANSWER, confidence=0.8)
        return flow

    async def fake_delivery(flow):
        flow.ctx.final_response = flow.ctx.orchestrator_response.text
        return flow

    return [
        Stage(fake_orch, "orchestrator", "working", "orchestrating"),
        Stage(filter_fn, "filter", "checking", "filtering"),
        Stage(fake_delivery, "delivery", "delivering", "filtering"),
    ]


def _run(monkeypatch, filter_fn, *, revised_text=None):
    rec, spawned = _patch_memory(monkeypatch)
    # the segment filter stage AND the recovery re-adjudication are the same fake filter
    monkeypatch.setattr(pipeline, "output_filter_run", filter_fn)
    # recovery re-runs the reasoning core directly (not the orchestrator stage) — fake it
    async def fake_run_loop(normalized, ports, ctx):
        return OrchestratorResponse(text=revised_text or _SUBSTANTIVE_ANSWER, confidence=0.9)
    monkeypatch.setattr("core.orchestrator.loop.run_loop", fake_run_loop)
    monkeypatch.setattr("core.orchestrator.utils.wiring.build_default_ports", lambda ctx: object())

    out = asyncio.run(pipeline.run("brief", session_id="s", user_id="u", stages=_custom_stages(filter_fn)))
    return rec, spawned, out


def _always_block():
    async def f(flow):
        flow.ctx.filter_blocked = True
        flow.ctx.blocked = True          # mirrors the real filter's flow.block(...) -> should_stop
        flow.ctx.filter_block_reason = "claim unsupported by findings"
        return flow
    return f


def _always_pass():
    async def f(flow):
        flow.ctx.filter_blocked = False
        return flow
    return f


def _block_then_pass():
    state = {"n": 0}
    async def f(flow):
        state["n"] += 1
        if state["n"] == 1:
            flow.ctx.filter_blocked = True
            flow.ctx.blocked = True
            flow.ctx.filter_block_reason = "first draft rejected"
        else:
            flow.ctx.filter_blocked = False
            flow.ctx.blocked = False
        return flow
    return f


def test_blocked_draft_never_writes_memory(monkeypatch):
    rec, spawned, out = _run(monkeypatch, _always_block())

    assert out.ctx.filter_blocked is True        # stayed blocked, fail-closed
    assert rec.record_calls == 0                 # NOTHING persisted for a blocked turn
    assert rec.proposals == []
    assert spawned == []                         # no distillation scheduled either
    _close(spawned)


def test_delivered_draft_writes_memory_exactly_once(monkeypatch):
    rec, spawned, out = _run(monkeypatch, _always_pass())

    assert out.ctx.filter_blocked is False
    assert rec.record_calls == 1                 # written exactly once, post-filter
    assert len(rec.proposals) == 1
    assert rec.proposals[0].store == MemoryStore.EPISODIC
    assert rec.last_user_id == "u"               # scoped to the right user
    assert len(spawned) == 1                     # distillation scheduled on the delivered turn
    _close(spawned)


def test_revision_then_delivered_writes_once_with_the_revised_answer(monkeypatch):
    rec, spawned, out = _run(monkeypatch, _block_then_pass(), revised_text="The REVISED, grounded answer. " * 8)

    assert out.ctx.filter_retry_count == 1       # one revision was enough
    assert rec.record_calls == 1                 # still exactly once — NOT on the blocked first draft
    assert len(rec.proposals) == 1
    assert "REVISED" in rec.proposals[0].content  # records the DELIVERED (revised) answer, not draft 1
    _close(spawned)
