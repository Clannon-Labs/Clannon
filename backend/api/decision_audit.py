"""
api/decision_audit.py — durable institutional decision-memory mirror (CB4).

One row per DERIVED decision point (core.orchestrator.utils.decision_log.
derive_record) — not a raw log dump. Append-only, user_id-scoped. Written by
run_driver at run completion for EVERY terminal outcome (delivered, blocked,
failed, cancelled) — a decision made on the way to a blocked/failed run is
still institutional memory. Read via GET /runs/{id}/decisions (owner-only).

Fail-closed: an empty user_id short-circuits both reads and writes — no
record is created or returned without a confirmed identity. Mirrors
api/audit.py's shape exactly (same DB helper, same scoping, same
public_json split), a parallel table, not a variant of the same one, since
the two audiences (security block review vs. decision-memory replay) query
independently.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from . import auth

if TYPE_CHECKING:
    from core.orchestrator.schemas import DecisionRecord


def write_decision_records(
    *,
    user_id: str,
    session_id: str,
    trace_id: str,
    records: "list[DecisionRecord]",
) -> None:
    """Append one durable row per derived decision record for this run.

    Best-effort by design at the call site (run_driver wraps this in a broad
    except) — a write fault here must never turn a finished run into a failed
    one. Fail-closed on identity: no rows written without a user_id.
    """
    if not user_id or not records:
        return
    with auth._db() as db:
        for rec in records:
            db.execute(
                "INSERT INTO decision_records "
                "(id, trace_id, user_id, session_id, turn, kind, decision, reasoning, "
                "participants_json, decided_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"dec_{secrets.token_hex(8)}", trace_id, user_id, session_id,
                    rec.turn, rec.kind, rec.decision, rec.reasoning,
                    json.dumps(rec.participants), rec.ts,
                ),
            )


def get_for_run(user_id: str, trace_id: str) -> list[dict]:
    """Decision records for one run, in the order they were decided, scoped to
    the run's owner. Empty list when `user_id` is empty (fail-closed) or when
    no records exist for this run/user combination."""
    if not user_id:
        return []
    with auth._db() as db:
        rows = db.execute(
            "SELECT * FROM decision_records WHERE trace_id = ? AND user_id = ? "
            "ORDER BY decided_at ASC",
            (trace_id, user_id),
        ).fetchall()
    return [_row_dict(r) for r in rows]


def _row_dict(row) -> dict:
    return {
        "id": row["id"],
        "trace_id": row["trace_id"],
        "user_id": row["user_id"],
        "session_id": row["session_id"],
        "turn": row["turn"],
        "kind": row["kind"],
        "decision": row["decision"],
        "reasoning": row["reasoning"],
        "participants": json.loads(row["participants_json"]),
        "decided_at": row["decided_at"],
    }


def public_json(row: dict) -> dict:
    """The camelCase API presentation of one decision record.

    Call this in the route layer; keep `get_for_run` returning raw columns
    for internal use and tests. `user_id` is omitted, same convention as
    `api/audit.py::public_json`."""
    return {
        "id": row["id"],
        "traceId": row["trace_id"],
        "sessionId": row["session_id"],
        "turn": row["turn"],
        "kind": row["kind"],
        "decision": row["decision"],
        "reasoning": row["reasoning"],
        "participants": row["participants"],
        "decidedAt": datetime.fromtimestamp(row["decided_at"], tz=timezone.utc).isoformat(),
    }
