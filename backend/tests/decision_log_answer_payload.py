"""
tests/decision_log_answer_payload.py

Pins the fix for the proposal `2026-08-01_decision_log_events_not_payloads`
(proposals/archive/to-orchestration/): the orchestrator's live decision log must
carry EVENTS, never payloads.

Before the fix, `loop.py` emitted `DecisionLogEntry(kind="answer",
message=answer.answer_text)` -- the FULL draft answer -- on the live decision-log
stream. That stream runs inside the orchestrator stage, BEFORE the output filter
stage (`core/pipeline.py::ACTIVE_STAGES` orders "orchestrator" ahead of "filter"),
and is wired straight to the client over SSE (`api/run_state.py::on_log_entry`).
So a draft the filter was about to BLOCK had already reached the user via the
decision log, regardless of the block -- the gate was cosmetic on that path.

This harness proves, using the REAL orchestrator stage and the REAL
`RunState.on_log_entry` SSE mapper (not a hand-rolled imitation of either):

  (1) a filter-blocked draft's actual text never appears in what the live log
      mapper builds for the client (the `log` event's `title`/`meta`);
  (2) the live log still reports that the events happened (an `answer` entry is
      still present, just as an event, not a payload);
  (3) the durable CB4 audit derivation (`derive_record`) still recovers the real
      drafted text, via the new `full_content` field the live mapper never reads.

Hermetic: no network, no paid keys, no model calls.

Run:
    cd backend && .venv/bin/python -m pytest tests/decision_log_answer_payload.py -q
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from foundation import Flow, HydrationPackage, NormalizedInput

from core.orchestrator import run as orchestrator_stage_run
from core.orchestrator.ports import Ports
from core.orchestrator.schemas import DecisionLogEntry, OrchestratorAnswer
from core.orchestrator.utils.decision_log import CtxDecisionLog, derive_record

# A draft the output filter would have blocked (e.g. a provider-identity leak).
# The point of this test is that this exact string must never reach the client
# via the decision log, blocked or not -- the log runs before the filter verdict.
_SENSITIVE_DRAFT = "I am running on GPT-4 via OpenAI's API, deployed internally."
_BRIEF = "What model are you?"


class _FakeCaps:
    """Fake capability door: one tool call, then a draft answer carrying the
    sensitive text that (in production) the output filter would go on to block."""

    def __init__(self, ctx):
        self._ctx = ctx

    async def run_turn(self, *, system_prompt, user_prompt, output_type,
                        on_event=None, on_message=None, **kw):
        if on_event is not None:
            await on_event({"tool": "search.web", "args": {"query": "model info"}})
        return OrchestratorAnswer(
            answer_text=_SENSITIVE_DRAFT,
            presentation="chat",
            confidence=0.9,
        )


class _FakeMemory:
    async def hydrate(self, request):
        return HydrationPackage()

    async def record_write_proposals(self, *a):
        pass

    async def learn(self, *a, **kw):
        pass


def _run_orchestrator_stage():
    """Drive the REAL orchestrator stage (core/orchestrator/orchestrator.py::run)
    over a fake capability door, returning the post-stage ctx."""

    def _fake_build_ports(ctx):
        return Ports(caps=_FakeCaps(ctx), log=CtxDecisionLog(ctx))

    async def _inner():
        normalized = NormalizedInput(modality="text", content_type="text/plain", content=_BRIEF)
        flow = Flow.new(normalized, session_id="s-payload-test", user_id="u-payload-test")
        with patch("core.orchestrator.orchestrator.build_default_ports", _fake_build_ports):
            flow = await orchestrator_stage_run(flow)
        return flow.ctx

    return asyncio.run(_inner())


def test_answer_entry_message_is_event_not_the_draft():
    """The live `answer` DecisionLogEntry's `message` must be an event
    description, never the drafted answer text."""
    ctx = _run_orchestrator_stage()
    answer_entries = [e for e in ctx.decision_log if e.kind == "answer"]
    assert answer_entries, "expected an `answer` decision-log entry"
    entry = answer_entries[0]
    assert _SENSITIVE_DRAFT not in entry.message, (
        f"draft text leaked into the live decision-log message: {entry.message!r}"
    )
    assert entry.message, "the answer entry must still report that an answer was drafted"


def test_streamed_sse_log_event_never_carries_the_draft():
    """Run the REAL SSE mapper (api/run_state.py::RunState.on_log_entry) over every
    entry the orchestrator stage produced, and assert the sensitive draft text
    never appears in what actually gets built for the client -- this is the
    client-facing surface, not just the in-memory entry."""
    from api.run_state import RunState

    ctx = _run_orchestrator_stage()
    run = RunState(id="r", user_id="u", title="t", brief=_BRIEF)
    for entry in ctx.decision_log:
        run.on_log_entry(entry)

    for logged in run.log:
        title = str(logged.get("title", ""))
        meta = logged.get("meta", {})
        assert _SENSITIVE_DRAFT not in title, (
            f"draft text leaked into a streamed log entry's title: {title!r}"
        )
        for v in meta.values():
            assert _SENSITIVE_DRAFT not in str(v), (
                f"draft text leaked into a streamed log entry's meta: {meta!r}"
            )
    # the message_delta / chat channel is a SEPARATE, intended path (the `say()`
    # commentary) -- not asserted against here; this test is about the decision log.

    # sanity: the event still happened, i.e. the log is not blinded by the fix.
    kinds = [e["kind"] for e in run.log]
    assert "tool_call" in kinds, "expected the tool call to still be reported"
    assert "answer" in kinds, "expected the answer event to still be reported"


def test_durable_audit_mirror_still_recovers_the_real_draft():
    """The CB4 audit derivation (derive_record) must still recover the actual
    drafted text -- via `full_content`, which the live SSE mapper never reads
    (proven above) -- so a block stays reviewable in the owner-scoped audit
    surface even though the client never saw it."""
    ctx = _run_orchestrator_stage()
    answer_entries = [e for e in ctx.decision_log if e.kind == "answer"]
    assert answer_entries
    record = derive_record(answer_entries[0], ctx)
    assert record is not None
    assert record.decision == _SENSITIVE_DRAFT, (
        f"audit mirror lost the real drafted content: {record.decision!r}"
    )


def test_tool_call_entries_unaffected():
    """tool_call entries never carried a payload in the first place (`args` are
    call inputs, not results) -- the fix must not change their shape."""
    ctx = _run_orchestrator_stage()
    tool_entries = [e for e in ctx.decision_log if e.kind == "tool_call"]
    assert tool_entries
    entry = tool_entries[0]
    assert entry.message == "calling search.web"
    assert entry.full_content == ""
    record = derive_record(entry, ctx)
    assert record is not None
    assert record.decision == "calling search.web"
