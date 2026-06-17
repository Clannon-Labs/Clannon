"""
The run store: in-memory live cache + SQLite persistence.

Live runs (which carry asyncio queues) stay in memory; finished runs are written
through to SQLite so history survives a restart. `RunStore` owns the lifecycle —
create / create_followup / set_feedback / persist — and the read paths that merge
live and persisted rows (get / list_for / session_turns), including the row<->RunState
mapping. The persistence SQL is encapsulated here, out of the route handlers and the
pure run record. The module-level `STORE` is the single shared instance.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

from . import auth
from .run_state import RunState, TERMINAL_STATUSES


class RunStore:
    """
    Live runs stay in memory (they carry asyncio queues); finished runs
    are persisted to SQLite so history survives server restarts.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def create(self, user_id: str, brief: str) -> RunState:
        rid = f"run_{secrets.token_hex(6)}"
        title = brief if len(brief) <= 64 else brief[:61].rstrip() + "…"
        # a root turn opens its own session
        run = RunState(id=rid, user_id=user_id, title=title, brief=brief, session_id=rid)
        self._runs[rid] = run
        return run

    def create_followup(self, user_id: str, ask: str, parent: RunState) -> RunState:
        """A follow-up is the NEXT TURN of the parent's session: it inherits the
        parent's `session_id` so the whole conversation is one session. The prior
        turns are replayed to the orchestrator as real chat history (built in
        `execute` via `_build_conversation`) — NOT stuffed into the input — so
        only the user's new `ask` passes through sanitize/verify, and the
        orchestrator genuinely continues the conversation."""
        rid = f"run_{secrets.token_hex(6)}"
        title = ask if len(ask) <= 64 else ask[:61].rstrip() + "…"
        run = RunState(
            id=rid, user_id=user_id, title=title, brief=ask,
            parent_run_id=parent.id, session_id=parent.session_id or parent.id,
        )
        self._runs[rid] = run
        return run

    def set_feedback(
        self, user_id: str, rid: str, rating: str | None, comment: str | None
    ) -> bool:
        """Attach a thumbs rating (+ optional note) to a run. Works whether the
        run is still live in memory or already persisted to SQLite."""
        live = self._runs.get(rid)
        if live is not None:
            if live.user_id != user_id:
                return False
            live.feedback_rating = rating
            live.feedback_comment = comment
            return True
        with auth._db() as db:
            cur = db.execute(
                "UPDATE runs SET feedback_rating=?, feedback_comment=?, feedback_at=? "
                "WHERE id=? AND user_id=?",
                (rating, comment, time.time(), rid, user_id),
            )
            return cur.rowcount > 0

    def request_cancel(self, user_id: str, rid: str) -> str:
        """Cooperatively cancel a run, scoped to its owner. Idempotent.

        Returns one of:
          - "notfound"   no such run for this user (→ 404),
          - "noop"       already terminal (delivered/blocked/failed/cancelled) — a
                         no-op success (→ 204),
          - "cancelling" the in-flight task was signalled to stop; the authoritative
                         `cancelled` status arrives over the SSE stream (→ 200),
          - "cancelled"  finalized directly (no live task to interrupt — an edge).

        Cancellation is cooperative: cancelling the run's asyncio task raises
        CancelledError at the next await inside the pipeline, unwinding through the
        stages' try/finally (so the Docker workspace and HTTP clients close), and
        execute() converts that into the `cancelled` terminal state. No output-filter
        delivery runs. Billing: any tokens already spent stay on the run (charged) —
        consistent with the usage-based model.
        """
        run = self.get(user_id, rid)
        if run is None:
            return "notfound"
        if run.status in TERMINAL_STATUSES:
            return "noop"
        run.cancel_requested = True
        task = run.task
        if task is not None and not task.done():
            task.cancel()
            return "cancelling"
        # No live task to interrupt (e.g. the run is between scheduling and start, or
        # already winding down). Finalize directly so the user still gets a clean stop.
        run.on_status("cancelled")
        run.finish()
        self.persist(run)
        return "cancelled"

    def delete_session(self, user_id: str, session_id: str) -> int:
        """Permanently delete every run in a session, scoped to its owner. Returns the
        count removed (0 = nothing to delete — an idempotent no-op).

        Live runs are marked `deleted` (so their execute() finally won't re-persist the
        row this just removed) and any in-flight task is cancelled, then dropped from the
        cache; persisted rows are deleted from SQLite. The conversation and its turns are
        removed; the assistant's learned, cross-session memory is RETAINED — it is user
        knowledge, not tied to one conversation.
        """
        removed = 0
        for rid, run in list(self._runs.items()):
            if run.user_id == user_id and (run.session_id or run.id) == session_id:
                run.deleted = True
                task = getattr(run, "task", None)
                if task is not None and not task.done():
                    task.cancel()
                self._runs.pop(rid, None)
                removed += 1
        with auth._db() as db:
            cur = db.execute(
                "DELETE FROM runs WHERE user_id=? AND session_id=?", (user_id, session_id)
            )
            removed += cur.rowcount or 0
        return removed

    def persist(self, run: RunState) -> None:
        """Write-through on terminal state — one row per finished run."""
        with auth._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO runs "
                "(id,user_id,title,brief,status,created_at,tokens_used,log_json,experts_json,report,message,memory_writes_json,"
                "feedback_rating,feedback_comment,parent_run_id,session_id,block_stage,artifacts_json,inputs_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.id, run.user_id, run.title, run.brief, run.status,
                    run.created_at, run.tokens_used, json.dumps(run.log),
                    json.dumps(list(run.experts.values())), run.report, run.message,
                    json.dumps(run.memory_writes),
                    run.feedback_rating, run.feedback_comment, run.parent_run_id,
                    run.session_id or run.id, run.block_stage, json.dumps(run.artifacts),
                    json.dumps(run.inputs),
                ),
            )
        # finished runs no longer need live queues in memory
        self._runs.pop(run.id, None)

    def _from_row(self, row: Any) -> RunState:
        run = RunState(
            id=row["id"], user_id=row["user_id"], title=row["title"],
            brief=row["brief"], status=row["status"], created_at=row["created_at"],
        )
        run.tokens_used = row["tokens_used"]
        run.log = json.loads(row["log_json"])
        run.experts = {e["id"]: e for e in json.loads(row["experts_json"])}
        run.report = row["report"]
        run.memory_writes = json.loads(row["memory_writes_json"])
        # columns added by later migrations — guard for rows/readers without them
        keys = row.keys()
        run.message = row["message"] if "message" in keys else None
        run.feedback_rating = row["feedback_rating"] if "feedback_rating" in keys else None
        run.feedback_comment = row["feedback_comment"] if "feedback_comment" in keys else None
        run.parent_run_id = row["parent_run_id"] if "parent_run_id" in keys else None
        # rows created before the session column default to a self-session
        run.session_id = (("session_id" in keys and row["session_id"]) or row["id"])
        run.block_stage = row["block_stage"] if "block_stage" in keys else None
        run.artifacts = json.loads(row["artifacts_json"]) if "artifacts_json" in keys and row["artifacts_json"] else []
        run.inputs = json.loads(row["inputs_json"]) if "inputs_json" in keys and row["inputs_json"] else []
        return run

    def get(self, user_id: str, rid: str) -> RunState | None:
        run = self._runs.get(rid)
        if run is not None:
            return run if run.user_id == user_id else None
        with auth._db() as db:
            row = db.execute(
                "SELECT * FROM runs WHERE id=? AND user_id=?", (rid, user_id)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_for(self, user_id: str) -> list[RunState]:
        live = {r.id: r for r in self._runs.values() if r.user_id == user_id}
        with auth._db() as db:
            rows = db.execute("SELECT * FROM runs WHERE user_id=?", (user_id,)).fetchall()
        merged = {row["id"]: self._from_row(row) for row in rows if row["id"] not in live}
        merged.update(live)
        return sorted(merged.values(), key=lambda r: r.created_at, reverse=True)

    def session_turns(self, user_id: str, session_id: str) -> list[RunState]:
        """Every turn of one session, oldest first — the chat thread."""
        live = {
            r.id: r
            for r in self._runs.values()
            if r.user_id == user_id and (r.session_id or r.id) == session_id
        }
        with auth._db() as db:
            rows = db.execute(
                "SELECT * FROM runs WHERE user_id=? AND session_id=?",
                (user_id, session_id),
            ).fetchall()
        merged = {row["id"]: self._from_row(row) for row in rows if row["id"] not in live}
        merged.update(live)
        return sorted(merged.values(), key=lambda r: r.created_at)


STORE = RunStore()
