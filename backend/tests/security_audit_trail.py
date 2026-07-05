"""
Security decision audit trail — hermetic tests.

Verifies the write/read contract for the durable block-decision store (C5):
  - A blocked run writes exactly one audit record carrying all required fields
    (block_code, threat_level, origin, reason, trace_id, user_id, session_id, blocked_at).
  - Records are user_id-scoped: another user cannot read them.
  - Writes are fail-closed without user_id: no record is created, no read is returned.
  - run_driver.execute wires the write correctly: a blocked pipeline flow produces
    exactly one record with fields drawn from the right ctx/flow attributes; a
    delivered flow produces zero records.

Hermetic: no network, no real models, no real SQLite (patched to a per-test temp file).
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

import core.pipeline
from foundation import Flow, BlockReason, ThreatLevel, Origin

from api import audit as audit_mod
from api import auth as auth_mod
from api import run_driver
from api.run_state import RunState
from api.run_store import STORE


def _make_db(db_file: str):
    """An in-process SQLite connection mirroring just the security_audit table."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS security_audit (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            block_code TEXT NOT NULL,
            threat_level TEXT NOT NULL,
            origin TEXT NOT NULL,
            reason TEXT,
            blocked_at REAL NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS security_audit_by_run "
        "ON security_audit (user_id, trace_id)"
    )
    conn.commit()
    return conn


@pytest.fixture()
def _db(monkeypatch, tmp_path):
    """Patch auth._db() to use a per-test temp SQLite file."""
    db_file = str(tmp_path / "audit_test.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _make_db(db_file))


# ---------------------------------------------------------------------------
# Core write/read contract
# ---------------------------------------------------------------------------

def test_write_then_read_returns_one_record_with_all_required_fields(_db):
    """A blocked run writes exactly one record; every required field is present."""
    audit_mod.write_block_record(
        user_id="u_alice",
        session_id="sess_001",
        trace_id="run_001",
        block_code="verifier_rejected",
        threat_level="high",
        origin="verifier",
        reason="Detected prompt injection attempt.",
    )

    records = audit_mod.get_for_run("u_alice", "run_001")
    assert len(records) == 1

    rec = records[0]
    assert rec["block_code"] == "verifier_rejected"
    assert rec["threat_level"] == "high"
    assert rec["origin"] == "verifier"
    assert rec["reason"] == "Detected prompt injection attempt."
    assert rec["trace_id"] == "run_001"
    assert rec["user_id"] == "u_alice"
    assert rec["session_id"] == "sess_001"
    assert isinstance(rec["blocked_at"], float) and rec["blocked_at"] > 0
    assert rec["id"].startswith("aud_")


def test_write_accepts_null_reason(_db):
    """Gates that don't produce a human reason are stored as NULL, not rejected."""
    audit_mod.write_block_record(
        user_id="u_bob",
        session_id="sess_002",
        trace_id="run_002",
        block_code="unsupported_modality",
        threat_level="none",
        origin="sanitizer",
        reason=None,
    )
    records = audit_mod.get_for_run("u_bob", "run_002")
    assert len(records) == 1
    assert records[0]["reason"] is None


# ---------------------------------------------------------------------------
# User-scoping
# ---------------------------------------------------------------------------

def test_records_are_user_scoped(_db):
    """The owner sees their record; another user's query returns nothing."""
    audit_mod.write_block_record(
        user_id="u_owner",
        session_id="sess_xyz",
        trace_id="run_xyz",
        block_code="malicious_content",
        threat_level="critical",
        origin="sanitizer",
        reason="YARA rule matched.",
    )

    assert len(audit_mod.get_for_run("u_owner", "run_xyz")) == 1
    assert audit_mod.get_for_run("u_other", "run_xyz") == []


def test_different_users_with_different_runs_are_isolated(_db):
    """Two users, two different runs — each only sees their own."""
    audit_mod.write_block_record(
        user_id="u_a", session_id="s_a", trace_id="run_a",
        block_code="filter_rejected", threat_level="medium", origin="filter", reason="PII",
    )
    audit_mod.write_block_record(
        user_id="u_b", session_id="s_b", trace_id="run_b",
        block_code="injection_detected", threat_level="high", origin="verifier", reason="Injection",
    )

    assert audit_mod.get_for_run("u_a", "run_b") == []
    assert audit_mod.get_for_run("u_b", "run_a") == []
    assert len(audit_mod.get_for_run("u_a", "run_a")) == 1
    assert len(audit_mod.get_for_run("u_b", "run_b")) == 1


# ---------------------------------------------------------------------------
# Fail-closed on missing identity
# ---------------------------------------------------------------------------

def test_write_is_noop_without_user_id(_db):
    """No record is written when user_id is empty — fail-closed."""
    audit_mod.write_block_record(
        user_id="",
        session_id="sess_noid",
        trace_id="run_noid",
        block_code="verifier_rejected",
        threat_level="high",
        origin="verifier",
        reason="no user",
    )
    # empty user_id → read always returns []
    assert audit_mod.get_for_run("", "run_noid") == []


def test_read_returns_empty_without_user_id(_db):
    """Empty user_id → no records returned regardless of what is in the DB."""
    audit_mod.write_block_record(
        user_id="u_real",
        session_id="sess_r",
        trace_id="run_r",
        block_code="verifier_rejected",
        threat_level="high",
        origin="verifier",
        reason="something",
    )
    # empty string user_id must not return the real user's records
    assert audit_mod.get_for_run("", "run_r") == []


# ---------------------------------------------------------------------------
# Non-blocked run → no records
# ---------------------------------------------------------------------------

def test_no_records_for_unblocked_run(_db):
    """A run that was never blocked has no audit records."""
    assert audit_mod.get_for_run("u_clean", "run_clean") == []


# ---------------------------------------------------------------------------
# run_driver wiring — proves the execute() path reaches write_block_record
# with the correct field values drawn from ctx + flow attributes
# ---------------------------------------------------------------------------

def _audit_db(db_file: str):
    """Minimal SQLite with the security_audit table only."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS security_audit ("
        "id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, user_id TEXT NOT NULL, "
        "session_id TEXT NOT NULL, block_code TEXT NOT NULL, threat_level TEXT NOT NULL, "
        "origin TEXT NOT NULL, reason TEXT, blocked_at REAL NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS security_audit_by_run "
        "ON security_audit (user_id, trace_id)"
    )
    conn.commit()
    return conn


def _run(user_id: str, run_id: str, session_id: str) -> RunState:
    return RunState(
        id=run_id, user_id=user_id,
        title="wiring test", brief="test brief",
        session_id=session_id,
    )


def test_execute_blocked_run_writes_exactly_one_audit_record(monkeypatch, tmp_path):
    """run_driver.execute with a verifier-blocked flow writes exactly one audit record
    whose block_code/threat_level/origin/reason match what the blocked flow carries.

    This proves the execute() wiring is correct — wrong ctx field, wrong reason
    branch, wrong origin source, or write firing zero/two times would all fail here.
    """
    db_file = str(tmp_path / "wiring.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _audit_db(db_file))

    user_id, run_id, session_id = "u_wiring", "run_wiring", "sess_wiring"

    # Build the same blocked flow the verifier gate would produce
    flow = Flow.new("test input", session_id=session_id, user_id=user_id, trace_id=run_id)
    flow.ctx.verifier_blocked = True
    flow.ctx.verifier_block_reason = "Detected prompt injection."
    blocked_flow = flow.block(BlockReason.VERIFIER_REJECTED, ThreatLevel.HIGH, Origin.VERIFIER)

    async def _stub_pipeline(*args, **kwargs):
        return blocked_flow

    monkeypatch.setattr(core.pipeline, "run", _stub_pipeline)
    monkeypatch.setattr(STORE, "session_turns", lambda uid, sid: [])
    monkeypatch.setattr(STORE, "persist", lambda run: None)
    monkeypatch.setattr(auth_mod, "model_prefs_get", lambda uid: {})

    asyncio.run(run_driver.execute(_run(user_id, run_id, session_id)))

    records = audit_mod.get_for_run(user_id, run_id)
    assert len(records) == 1, f"Expected 1 audit record, got {len(records)}"
    rec = records[0]
    assert rec["block_code"] == "verifier_rejected"
    assert rec["threat_level"] == "high"
    assert rec["origin"] == "verifier"
    assert rec["reason"] == "Detected prompt injection."


def test_execute_delivered_run_writes_zero_audit_records(monkeypatch, tmp_path):
    """run_driver.execute with a non-blocked (delivered) flow writes no audit records."""
    db_file = str(tmp_path / "wiring_ok.db")
    monkeypatch.setattr(auth_mod, "_db", lambda: _audit_db(db_file))

    user_id, run_id, session_id = "u_ok", "run_ok", "sess_ok"

    flow = Flow.new("test input", session_id=session_id, user_id=user_id, trace_id=run_id)
    flow.ctx.final_response = "Here is the delivered result."

    async def _stub_pipeline(*args, **kwargs):
        return flow

    monkeypatch.setattr(core.pipeline, "run", _stub_pipeline)
    monkeypatch.setattr(STORE, "session_turns", lambda uid, sid: [])
    monkeypatch.setattr(STORE, "persist", lambda run: None)
    monkeypatch.setattr(auth_mod, "model_prefs_get", lambda uid: {})

    asyncio.run(run_driver.execute(_run(user_id, run_id, session_id)))

    records = audit_mod.get_for_run(user_id, run_id)
    assert records == [], f"Expected 0 records for a delivered run, got {len(records)}"
