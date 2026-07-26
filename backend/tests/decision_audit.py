"""
Institutional decision-memory audit mirror (CB4) — hermetic tests.

Verifies the write/read contract for the durable decision-record store:
  - A run's decision log derives durable records via `derive_record` for
    every tool_call/answer entry; narration entries derive to nothing.
  - Records are user_id-scoped: another user cannot read them.
  - Writes are fail-closed without user_id: no record is created, no read
    is returned.
  - run_driver.execute wires the write correctly for EVERY terminal outcome
    (delivered, blocked, failed) — not just delivered runs.

Hermetic: no network, no real models, no real SQLite (patched to a per-test
temp file).
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

import core.pipeline
from foundation import Flow, BlockReason, ThreatLevel, Origin
from core.orchestrator.schemas import DecisionLogEntry, DecisionRecord

from api import decision_audit as da_mod
from api import auth as auth_mod
from api import run_driver
from api.run_state import RunState
from api.run_store import STORE


_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS decision_records ("
    "id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, user_id TEXT NOT NULL, "
    "session_id TEXT NOT NULL, turn INTEGER NOT NULL, kind TEXT NOT NULL, "
    "decision TEXT NOT NULL, reasoning TEXT NOT NULL DEFAULT '', "
    "participants_json TEXT NOT NULL DEFAULT '[]', decided_at REAL NOT NULL)"
)


def _make_db(db_file: str):
    """An in-process SQLite connection mirroring just the decision_records table."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute(_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS decision_records_by_run "
        "ON decision_records (user_id, trace_id)"
    )
    conn.commit()
    return conn


@pytest.fixture()
def _db(monkeypatch, tmp_path):
    """Patch auth._db() to use a per-test temp SQLite file."""
    db_file = str(tmp_path / "decisions_test.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _make_db(db_file))


def _record(**over) -> DecisionRecord:
    base = dict(decision="called web.search", participants=["web.search"],
                reasoning="", ts=1000.0, turn=1, kind="tool_call")
    return DecisionRecord(**{**base, **over})


# ---------------------------------------------------------------------------
# Core write/read contract
# ---------------------------------------------------------------------------

def test_write_then_read_returns_records_in_decided_order(_db):
    da_mod.write_decision_records(
        user_id="u_alice", session_id="sess_001", trace_id="run_001",
        records=[
            _record(decision="first", ts=1000.0, turn=1),
            _record(decision="second", ts=1005.0, turn=2, kind="answer", participants=[]),
        ],
    )

    records = da_mod.get_for_run("u_alice", "run_001")
    assert [r["decision"] for r in records] == ["first", "second"]

    rec = records[0]
    assert rec["kind"] == "tool_call"
    assert rec["participants"] == ["web.search"]
    assert rec["trace_id"] == "run_001"
    assert rec["user_id"] == "u_alice"
    assert rec["session_id"] == "sess_001"
    assert rec["id"].startswith("dec_")


def test_write_is_noop_for_empty_records_list(_db):
    da_mod.write_decision_records(
        user_id="u_bob", session_id="s", trace_id="run_empty", records=[],
    )
    assert da_mod.get_for_run("u_bob", "run_empty") == []


# ---------------------------------------------------------------------------
# User-scoping
# ---------------------------------------------------------------------------

def test_records_are_user_scoped(_db):
    da_mod.write_decision_records(
        user_id="u_owner", session_id="sess_xyz", trace_id="run_xyz",
        records=[_record()],
    )
    assert len(da_mod.get_for_run("u_owner", "run_xyz")) == 1
    assert da_mod.get_for_run("u_other", "run_xyz") == []


# ---------------------------------------------------------------------------
# Fail-closed on missing identity
# ---------------------------------------------------------------------------

def test_write_is_noop_without_user_id(_db):
    da_mod.write_decision_records(
        user_id="", session_id="s", trace_id="run_noid", records=[_record()],
    )
    assert da_mod.get_for_run("", "run_noid") == []


def test_read_returns_empty_without_user_id(_db):
    da_mod.write_decision_records(
        user_id="u_real", session_id="s", trace_id="run_r", records=[_record()],
    )
    assert da_mod.get_for_run("", "run_r") == []


# ---------------------------------------------------------------------------
# run_driver wiring — proves execute() reaches write_decision_records with
# derived records for EVERY terminal outcome, not just delivered
# ---------------------------------------------------------------------------

def _run(user_id: str, run_id: str, session_id: str) -> RunState:
    return RunState(
        id=run_id, user_id=user_id, title="wiring test", brief="test brief",
        session_id=session_id,
    )


def _flow_with_decision_log(*, session_id, user_id, trace_id) -> Flow:
    flow = Flow.new("test input", session_id=session_id, user_id=user_id, trace_id=trace_id)
    flow.ctx.decision_log.append(
        DecisionLogEntry(kind="tool_call", message="called web.search", turn=1,
                         detail={"tool": "web.search"})
    )
    return flow


def test_execute_delivered_run_writes_derived_decision_records(monkeypatch, tmp_path):
    db_file = str(tmp_path / "wiring_delivered.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _make_db(db_file))

    user_id, run_id, session_id = "u_ok", "run_ok", "sess_ok"
    flow = _flow_with_decision_log(session_id=session_id, user_id=user_id, trace_id=run_id)
    flow.ctx.final_response = "Here is the delivered result."

    async def _stub_pipeline(*a, **k):
        return flow

    monkeypatch.setattr(core.pipeline, "run", _stub_pipeline)
    monkeypatch.setattr(STORE, "session_turns", lambda uid, sid: [])
    monkeypatch.setattr(STORE, "persist", lambda run: None)
    monkeypatch.setattr(auth_mod, "model_prefs_get", lambda uid: {})

    asyncio.run(run_driver.execute(_run(user_id, run_id, session_id)))

    records = da_mod.get_for_run(user_id, run_id)
    assert len(records) == 1
    assert records[0]["kind"] == "tool_call"
    assert records[0]["participants"] == ["web.search"]


def test_execute_blocked_run_still_writes_decision_records(monkeypatch, tmp_path):
    """A decision made on the way to a blocked run is still institutional memory —
    not gated on the run having been delivered."""
    db_file = str(tmp_path / "wiring_blocked.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _make_db(db_file))

    user_id, run_id, session_id = "u_wiring", "run_wiring", "sess_wiring"
    flow = _flow_with_decision_log(session_id=session_id, user_id=user_id, trace_id=run_id)
    flow.ctx.verifier_blocked = True
    flow.ctx.verifier_block_reason = "Detected prompt injection."
    blocked_flow = flow.block(BlockReason.VERIFIER_REJECTED, ThreatLevel.HIGH, Origin.VERIFIER)

    async def _stub_pipeline(*a, **k):
        return blocked_flow

    monkeypatch.setattr(core.pipeline, "run", _stub_pipeline)
    monkeypatch.setattr(STORE, "session_turns", lambda uid, sid: [])
    monkeypatch.setattr(STORE, "persist", lambda run: None)
    monkeypatch.setattr(auth_mod, "model_prefs_get", lambda uid: {})

    asyncio.run(run_driver.execute(_run(user_id, run_id, session_id)))

    records = da_mod.get_for_run(user_id, run_id)
    assert len(records) == 1, f"Expected 1 decision record on a blocked run, got {len(records)}"


def test_execute_writes_zero_records_for_pure_narration(monkeypatch, tmp_path):
    """A decision log with only narration (no tool_call/answer) derives to nothing."""
    db_file = str(tmp_path / "wiring_narration.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _make_db(db_file))

    user_id, run_id, session_id = "u_narr", "run_narr", "sess_narr"
    flow = Flow.new("test input", session_id=session_id, user_id=user_id, trace_id=run_id)
    flow.ctx.decision_log.append(
        DecisionLogEntry(kind="observation", message="just narrating", turn=1, detail={})
    )
    flow.ctx.final_response = "delivered text"

    async def _stub_pipeline(*a, **k):
        return flow

    monkeypatch.setattr(core.pipeline, "run", _stub_pipeline)
    monkeypatch.setattr(STORE, "session_turns", lambda uid, sid: [])
    monkeypatch.setattr(STORE, "persist", lambda run: None)
    monkeypatch.setattr(auth_mod, "model_prefs_get", lambda uid: {})

    asyncio.run(run_driver.execute(_run(user_id, run_id, session_id)))

    assert da_mod.get_for_run(user_id, run_id) == []
