"""
Run execution + live streaming.

Drives the same stage chain as core.pipeline (imported, not duplicated)
but steps it stage-by-stage so the web layer can emit status transitions,
and swaps ctx.decision_log for an observing list so every DecisionLogEntry
the orchestrator emits is pushed to subscribers the moment it lands —
no pipeline code is modified. Event shapes mirror the frontend RunEvent
union exactly.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable

from foundation import Flow

from core.llm import model_overrides
from core.pipeline import ACTIVE_STAGES

from . import auth, config


def build_model_overrides(user_id: str) -> dict[str, str]:
    """
    Translate the user's stored model preferences into pipeline role
    overrides ("role" -> "provider:model"). Locked layers are never
    overridable; the "experts" default applies to every expert role
    unless a per-expert choice exists.
    """
    with auth._db() as db:
        prefs = {
            row["layer"]: row["model"]
            for row in db.execute(
                "SELECT layer, model FROM model_prefs WHERE user_id=?", (user_id,)
            )
        }
    overrides: dict[str, str] = {}
    locked = {e["layer"] for e in config.MODEL_CATALOG if e["locked"]}
    if "orchestrator" in prefs and "orchestrator" not in locked:
        overrides["orchestrator"] = config.qualify_model(prefs["orchestrator"])
    for expert in config.EXPERTS:
        chosen = prefs.get(f"expert:{expert['key']}") or prefs.get("experts")
        if chosen:
            overrides[expert["role"]] = config.qualify_model(chosen)
    return overrides

# one display status per ACTIVE_STAGES entry (intake, sanitizer, normalizer,
# verifier, orchestrator, output filter, delivery)
_STAGE_STATUS = [
    "sanitizing",
    "sanitizing",
    "verifying",
    "verifying",
    "orchestrating",
    "filtering",
    "filtering",
]

_TERMINAL = {"delivered", "blocked", "failed"}
_REPORT_CHUNK_WORDS = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ObservedLog(list):
    """ctx.decision_log replacement: appends also notify the run."""

    def __init__(self, on_entry: Callable[[Any], None]) -> None:
        super().__init__()
        self._on_entry = on_entry

    def append(self, entry: Any) -> None:  # the sink only ever appends
        super().append(entry)
        self._on_entry(entry)


@dataclass
class RunState:
    id: str
    user_id: str
    title: str
    brief: str
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    events: list[dict] = field(default_factory=list)     # buffered for replay
    log: list[dict] = field(default_factory=list)
    experts: dict[str, dict] = field(default_factory=dict)
    report: str | None = None
    tokens_used: int = 0
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    memory_writes: list[dict] = field(default_factory=list)

    def emit(self, event: dict) -> None:
        self.events.append(event)
        for q in list(self.subscribers):
            q.put_nowait(event)

    def finish(self) -> None:
        for q in list(self.subscribers):
            q.put_nowait(None)  # sentinel: stream over

    # ---- mappers -------------------------------------------------------

    def on_status(self, status: str) -> None:
        self.status = status
        self.emit({"type": "status", "status": status})

    def on_log_entry(self, entry: Any) -> None:
        mapped = {
            "id": f"log_{secrets.token_hex(6)}",
            "ts": _now(),
            "kind": getattr(entry, "kind", "observation"),
            "title": getattr(entry, "message", str(entry)),
        }
        detail = getattr(entry, "detail", None) or {}
        if detail:
            mapped["meta"] = {str(k): str(v) for k, v in detail.items()}
        self.log.append(mapped)
        self.emit({"type": "log", "entry": mapped})
        if mapped["kind"] == "expert_spawn":
            eid = f"e{len(self.experts) + 1}"
            expert = {
                "id": eid,
                "name": str(detail.get("expert", mapped["title"]))[:60],
                "domain": str(detail.get("domain", "expert")),
                "status": "working",
                "toolCalls": 0,
            }
            self.experts[eid] = expert
            self.emit({"type": "expert", "expert": expert})

    def on_experts_settled(self, expert_calls: list[Any]) -> None:
        """After orchestration: reconcile expert states from ctx.expert_calls."""
        for i, record in enumerate(expert_calls):
            eid = f"e{i + 1}"
            summary = None
            if isinstance(record.result, dict):
                summary = record.result.get("summary") or record.result.get("text")
            expert = self.experts.get(eid) or {
                "id": eid,
                "name": record.expert_name,
                "domain": str(record.arguments.get("domain", "expert"))[:40],
                "toolCalls": len(record.sub_tool_calls),
            }
            expert.update(
                name=record.expert_name,
                status="done" if record.success else "failed",
                toolCalls=len(record.sub_tool_calls),
            )
            if summary:
                expert["summary"] = str(summary)[:400]
            self.experts[eid] = expert
            self.emit({"type": "expert", "expert": expert})

    async def stream_report(self, text: str) -> None:
        words = text.split(" ")
        for i in range(0, len(words), _REPORT_CHUNK_WORDS):
            chunk = " ".join(words[i : i + _REPORT_CHUNK_WORDS])
            if i + _REPORT_CHUNK_WORDS < len(words):
                chunk += " "
            self.emit({"type": "report_delta", "text": chunk})
            await asyncio.sleep(0.02)
        self.report = text
        self.emit({"type": "report_done"})

    # ---- REST shapes ----------------------------------------------------

    def summary_json(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "createdAt": self.created_at,
            "tokensUsed": self.tokens_used,
            "expertCount": len(self.experts),
        }

    def full_json(self) -> dict:
        return {
            **self.summary_json(),
            "brief": self.brief,
            "decisionLog": self.log,
            "experts": list(self.experts.values()),
            "report": self.report,
            "sources": [],  # structured sources arrive with the citation expert
        }


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
        run = RunState(id=rid, user_id=user_id, title=title, brief=brief)
        self._runs[rid] = run
        return run

    def persist(self, run: RunState) -> None:
        """Write-through on terminal state — one row per finished run."""
        with auth._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO runs "
                "(id,user_id,title,brief,status,created_at,tokens_used,log_json,experts_json,report,memory_writes_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.id, run.user_id, run.title, run.brief, run.status,
                    run.created_at, run.tokens_used, json.dumps(run.log),
                    json.dumps(list(run.experts.values())), run.report,
                    json.dumps(run.memory_writes),
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


STORE = RunStore()


async def execute(run: RunState) -> None:
    """Drive the real pipeline for one run, emitting events as it goes."""
    flow: Flow[Any] = Flow.new(run.brief, session_id=run.id, user_id=run.user_id)
    # observe the decision log without touching pipeline code
    flow.ctx.decision_log = _ObservedLog(run.on_log_entry)

    try:
        # user model preferences apply to every stage in this run
        with model_overrides(build_model_overrides(run.user_id)):
            for stage, status in zip(ACTIVE_STAGES, _STAGE_STATUS):
                if flow.should_stop:
                    break
                if status != run.status:
                    run.on_status(status)
                flow = await stage(flow)
                if stage.__module__.startswith("core.orchestrator"):
                    run.on_experts_settled(flow.ctx.expert_calls)

            ctx = flow.ctx
            run.memory_writes = [
                {
                    "content": getattr(w, "content", str(w)),
                    "rationale": getattr(w, "rationale", ""),
                    "ts": _now(),
                }
                for w in ctx.memory_writes_requested
            ]

            if ctx.blocked or ctx.sanitization_blocked or ctx.verifier_blocked or ctx.filter_blocked:
                run.on_status("blocked")
            elif ctx.failed:
                if ctx.failure_error:
                    run.on_log_entry(
                        type("E", (), {
                            "kind": "error",
                            "message": str(ctx.failure_error)[:300],
                            "detail": {},
                        })()
                    )
                run.on_status("failed")
            else:
                text = ctx.final_response or (
                    ctx.orchestrator_response.text if ctx.orchestrator_response else ""
                )
                run.on_status("delivered")
                await run.stream_report(str(text))

    except Exception as exc:  # the web layer never lets a run take the server down
        run.on_log_entry(
            type("E", (), {"kind": "error", "message": f"pipeline error: {exc}", "detail": {}})()
        )
        run.on_status("failed")
    finally:
        run.finish()
        STORE.persist(run)


async def sse_stream(run: RunState) -> AsyncGenerator[str, None]:
    """Replay buffered events, then live ones, as SSE frames."""
    queue: asyncio.Queue = asyncio.Queue()
    run.subscribers.append(queue)
    try:
        for event in list(run.events):
            yield f"data: {json.dumps(event)}\n\n"
        if run.status in _TERMINAL and run.report is not None:
            return
        while True:
            event = await queue.get()
            if event is None:
                return
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        run.subscribers.remove(queue)
