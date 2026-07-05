"""
Tests for CB4's emit-side contract: DecisionRecord + derive_record()
(core/orchestrator/schemas.py, core/orchestrator/utils/decision_log.py).

Acceptance matrix (per the ratified design):
  (a) non-decision kinds (message, warning) derive to None -- only tool_call/
      answer are decision points
  (b) tool_call -> decision/participants derived correctly from `detail`
  (c) answer -> participants is the FULL authoritative cast from
      ctx.expert_calls/tool_calls, not just what streamed live
  (d) reasoning-attribution regression: the worked trace from the design doc --
      a tool_call correctly inherits an immediately-preceding say(), but a LATER
      answer does NOT inherit that same say() once a decision point (the
      tool_call) sits between them
  (e) purity: derive_record makes no network/model/subprocess call
"""

from __future__ import annotations

import socket
import subprocess
import urllib.request

from foundation import ExpertCallRecord, ToolCallRecord, VrakshaContext

from core.orchestrator.schemas import DecisionLogEntry, DecisionRecord
from core.orchestrator.utils.decision_log import derive_record


def _ctx() -> VrakshaContext:
    return VrakshaContext.new("s1", user_id="u1")


# ─── (a) non-decision kinds derive to None ─────────────────────────────────

def test_message_kind_derives_to_none():
    ctx = _ctx()
    entry = DecisionLogEntry(kind="message", message="thinking out loud")
    assert derive_record(entry, ctx) is None


def test_warning_kind_derives_to_none():
    ctx = _ctx()
    entry = DecisionLogEntry(kind="warning", message="answering in degraded mode")
    assert derive_record(entry, ctx) is None


# ─── (b) tool_call -> decision/participants ────────────────────────────────

def test_tool_call_derives_decision_and_participant():
    ctx = _ctx()
    entry = DecisionLogEntry(
        kind="tool_call", message="calling search.web",
        detail={"tool": "search.web", "args": {"query": "x"}},
    )
    record = derive_record(entry, ctx)
    assert isinstance(record, DecisionRecord)
    assert record.decision == "calling search.web"
    assert record.participants == ["search.web"]
    assert record.kind == "tool_call"
    assert record.ts > 0


def test_tool_call_with_no_tool_key_has_empty_participants():
    """Defensive: a malformed/missing detail must not crash the derivation."""
    ctx = _ctx()
    entry = DecisionLogEntry(kind="tool_call", message="calling ?", detail={})
    record = derive_record(entry, ctx)
    assert record is not None and record.participants == []


# ─── (c) answer -> full authoritative cast from ctx, not just live stream ──

def test_answer_participants_is_full_cast_from_ctx():
    ctx = _ctx()
    ctx.tool_calls.append(ToolCallRecord(tool_name="search.web", arguments={}, success=True))
    ctx.expert_calls.append(ExpertCallRecord(expert_name="web.research", arguments={}, success=True))
    entry = DecisionLogEntry(kind="answer", message="final answer text")
    record = derive_record(entry, ctx)
    assert record is not None
    assert record.decision == "final answer text"
    assert record.participants == ["search.web", "web.research"]  # sorted


def test_answer_with_no_calls_has_empty_participants():
    ctx = _ctx()
    entry = DecisionLogEntry(kind="answer", message="direct answer, no tools used")
    record = derive_record(entry, ctx)
    assert record is not None and record.participants == []


# ─── (d) reasoning-attribution regression (the worked trace) ───────────────

def test_reasoning_inherits_immediately_preceding_say():
    """A tool_call whose immediately preceding entry is a `say()` message
    correctly attributes that message as its reasoning."""
    ctx = _ctx()
    msg = DecisionLogEntry(kind="message", message="Let me have the research expert look into this.")
    call = DecisionLogEntry(kind="tool_call", message="calling web.research", detail={"tool": "web.research"})
    ctx.decision_log.extend([msg, call])

    record = derive_record(call, ctx)
    assert record is not None
    assert record.reasoning == "Let me have the research expert look into this."


def test_reasoning_does_not_leak_across_an_intervening_decision():
    """THE regression case from the design doc's worked trace: message -> tool_call
    -> answer. The answer must NOT inherit the message's reasoning, because the
    tool_call (a decision point) sits between them -- that reasoning belongs to
    the tool_call, not to the later, unrelated answer."""
    ctx = _ctx()
    msg = DecisionLogEntry(kind="message", message="Let me have the research expert look into this.")
    call = DecisionLogEntry(kind="tool_call", message="calling web.research", detail={"tool": "web.research"})
    answer = DecisionLogEntry(kind="answer", message="Here is what I found.")
    ctx.decision_log.extend([msg, call, answer])

    call_record = derive_record(call, ctx)
    answer_record = derive_record(answer, ctx)

    assert call_record is not None and call_record.reasoning == (
        "Let me have the research expert look into this."
    )
    assert answer_record is not None and answer_record.reasoning == "", (
        f"answer must not inherit an earlier decision's reasoning, got: "
        f"{answer_record.reasoning!r}"
    )


def test_reasoning_empty_when_no_preceding_message():
    ctx = _ctx()
    entry = DecisionLogEntry(kind="tool_call", message="calling search.web", detail={"tool": "search.web"})
    ctx.decision_log.append(entry)
    record = derive_record(entry, ctx)
    assert record is not None and record.reasoning == ""


# ─── (e) purity: no network / model / subprocess access ────────────────────

def test_derive_record_makes_no_external_calls(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: calls.append("socket") or [])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append("subprocess"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: calls.append("urllib"))

    ctx = _ctx()
    msg = DecisionLogEntry(kind="message", message="thinking")
    call = DecisionLogEntry(kind="tool_call", message="calling search.web", detail={"tool": "search.web"})
    answer = DecisionLogEntry(kind="answer", message="done")
    ctx.tool_calls.append(ToolCallRecord(tool_name="search.web", arguments={}, success=True))
    for entry in (msg, call, answer):
        ctx.decision_log.append(entry)
        derive_record(entry, ctx)

    assert calls == [], f"derive_record made unexpected external call(s): {calls}"
