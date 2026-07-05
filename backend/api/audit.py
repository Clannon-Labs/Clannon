"""
api/audit.py — durable security-decision audit trail.

One record per blocked run. Append-only, user_id-scoped. Written by
run_driver at run completion when any security gate blocked the request;
read via GET /runs/{id}/audit (owner-only).

Fail-closed: an empty user_id short-circuits both reads and writes — no
record is created or returned without a confirmed identity.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

from . import auth


def write_block_record(
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    block_code: str,
    threat_level: str,
    origin: str,
    reason: str | None,
) -> None:
    """Append one security block decision to the audit log.

    All parameters are required except `reason` (which may be None when the
    blocking gate did not produce a human-readable explanation). The record is
    keyed by `trace_id` (the run id) and scoped to `user_id`.
    """
    if not user_id:
        return
    record_id = f"aud_{secrets.token_hex(8)}"
    with auth._db() as db:
        db.execute(
            "INSERT INTO security_audit "
            "(id, trace_id, user_id, session_id, block_code, threat_level, origin, reason, blocked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id, trace_id, user_id, session_id,
                block_code, threat_level, origin, reason, time.time(),
            ),
        )


def get_for_run(user_id: str, trace_id: str) -> list[dict]:
    """Audit records for one run, scoped to its owner.

    Returns an empty list when `user_id` is empty (fail-closed) or when no
    records exist for this run/user combination.
    """
    if not user_id:
        return []
    with auth._db() as db:
        rows = db.execute(
            "SELECT * FROM security_audit WHERE trace_id = ? AND user_id = ?",
            (trace_id, user_id),
        ).fetchall()
    return [_row_dict(r) for r in rows]


def _row_dict(row) -> dict:
    return {
        "id": row["id"],
        "trace_id": row["trace_id"],
        "user_id": row["user_id"],
        "session_id": row["session_id"],
        "block_code": row["block_code"],
        "threat_level": row["threat_level"],
        "origin": row["origin"],
        "reason": row["reason"],
        "blocked_at": row["blocked_at"],
    }


def public_json(row: dict) -> dict:
    """The camelCase API presentation of one audit record.

    Call this in the route layer; keep `get_for_run` returning raw columns
    (snake_case) for internal use and tests. `user_id` is omitted — the caller
    IS that user and no other API response echoes it back.
    """
    return {
        "id": row["id"],
        "traceId": row["trace_id"],
        "sessionId": row["session_id"],
        "blockCode": row["block_code"],
        "threatLevel": row["threat_level"],
        "origin": row["origin"],
        "reason": row["reason"],
        "blockedAt": datetime.fromtimestamp(row["blocked_at"], tz=timezone.utc).isoformat(),
    }
