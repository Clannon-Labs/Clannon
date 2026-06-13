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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable

from foundation import Flow, constants

from core.llm import model_overrides
from core.pipeline import ACTIVE_STAGES
from security.filter import run as _OUTPUT_FILTER

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


def _process_summary(run: "RunState") -> str:
    """A factual recap of what a turn actually did — which experts ran and which
    tools were called — so a follow-up orchestrator can answer questions about
    its own prior work instead of guessing. Built from the persisted decision
    log + expert states; never fabricated."""
    experts = [e for e in run.experts.values()]
    tool_calls = [
        e.get("title", "") for e in run.log if e.get("kind") == "tool_call"
    ]
    if not experts and not tool_calls:
        return (
            "No experts or tools were used — this turn was answered directly "
            "from the model's own knowledge."
        )
    lines: list[str] = []
    if experts:
        lines.append(
            "Experts run: "
            + "; ".join(
                f"{e.get('name', 'expert')}"
                + (f" ({e['domain']})" if e.get("domain") else "")
                + (f" — {e['toolCalls']} tool calls" if e.get("toolCalls") else "")
                for e in experts
            )
        )
    if tool_calls:
        shown = tool_calls[:12]
        lines.append("Tools called: " + "; ".join(shown))
        if len(tool_calls) > len(shown):
            lines.append(f"(+{len(tool_calls) - len(shown)} more tool calls)")
    return "\n".join(lines)


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
    feedback_rating: str | None = None       # "up" | "down" | None
    feedback_comment: str | None = None
    parent_run_id: str | None = None         # set on follow-up runs
    # which gate blocked, if any: "sanitize" | "verify" | "filter" | "security".
    # input-side gates (sanitize/verify) mean nothing reached the models; the
    # output filter means a draft was produced then held back.
    block_stage: str | None = None
    # the session this turn belongs to. Root turns own their session (= id);
    # follow-ups inherit the parent's, so the whole chat is one session.
    session_id: str = ""

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
            "sessionId": self.session_id or self.id,
        }

    def full_json(self) -> dict:
        return {
            **self.summary_json(),
            "brief": self.brief,
            "decisionLog": self.log,
            "experts": list(self.experts.values()),
            "report": self.report,
            "sources": [],  # structured sources arrive with the citation expert
            "feedbackRating": self.feedback_rating,
            "feedbackComment": self.feedback_comment,
            "parentRunId": self.parent_run_id,
            "sessionId": self.session_id or self.id,
            "blockStage": self.block_stage,
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

    def persist(self, run: RunState) -> None:
        """Write-through on terminal state — one row per finished run."""
        with auth._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO runs "
                "(id,user_id,title,brief,status,created_at,tokens_used,log_json,experts_json,report,memory_writes_json,"
                "feedback_rating,feedback_comment,parent_run_id,session_id,block_stage) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.id, run.user_id, run.title, run.brief, run.status,
                    run.created_at, run.tokens_used, json.dumps(run.log),
                    json.dumps(list(run.experts.values())), run.report,
                    json.dumps(run.memory_writes),
                    run.feedback_rating, run.feedback_comment, run.parent_run_id,
                    run.session_id or run.id, run.block_stage,
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
        run.feedback_rating = row["feedback_rating"] if "feedback_rating" in keys else None
        run.feedback_comment = row["feedback_comment"] if "feedback_comment" in keys else None
        run.parent_run_id = row["parent_run_id"] if "parent_run_id" in keys else None
        # rows created before the session column default to a self-session
        run.session_id = (("session_id" in keys and row["session_id"]) or row["id"])
        run.block_stage = row["block_stage"] if "block_stage" in keys else None
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

# how many prior turns to replay as chat history — bounds the context the
# orchestrator carries on a long-running session
_MAX_HISTORY_TURNS = 8


def _build_conversation(run: RunState) -> list[dict]:
    """Replay this session's earlier turns as neutral chat history (oldest first):
    each delivered turn becomes a user message (the brief) and an assistant
    message (the report, with a short note of which experts/tools produced it so
    the model retains that provenance). Only turns BEFORE this one are included."""
    session = run.session_id or run.id
    convo: list[dict] = []
    for turn in STORE.session_turns(run.user_id, session):
        if turn.id == run.id or turn.created_at >= run.created_at:
            continue
        convo.append({"role": "user", "content": turn.brief})
        report = (turn.report or "").strip()
        if report:
            process = _process_summary(turn)
            assistant = report
            if process and not process.startswith("No experts"):
                assistant += f"\n\n[How I produced this: {process}]"
            convo.append({"role": "assistant", "content": assistant})
        else:
            # a turn that produced no report still happened — tell the orchestrator
            # it was blocked/failed so it can recover (e.g. on a "try again")
            note = {
                "blocked": "was stopped by the security pipeline and no answer was delivered",
                "failed": "did not complete due to a pipeline error",
            }.get(turn.status, "produced no answer")
            convo.append({
                "role": "assistant",
                "content": f"[The previous turn {note}. Adjust and try again.]",
            })
    # keep the most recent turns if the session is long (2 messages per turn)
    return convo[-(_MAX_HISTORY_TURNS * 2):]


async def _recover_from_filter_block(flow: Flow[Any], run: RunState) -> Flow[Any]:
    """Bounded output-filter recovery. ONLY the output filter — which rejects the
    orchestrator's own DRAFT — is retriable here; input-side blocks (sanitize /
    verify) reject the brief and need a new one from the user. On each retry the
    filter's reason is handed back to the orchestrator, it produces a corrected
    draft, and the filter adjudicates again. After MAX_OUTPUT_RETRIES we stop and
    the run stays blocked — fail closed; the filter is always the final authority."""
    from core.orchestrator.loop import run_loop
    from core.orchestrator.utils.wiring import build_default_ports

    ctx = flow.ctx
    while (
        ctx.filter_blocked
        and ctx.normalized_input is not None
        and ctx.filter_retry_count < constants.MAX_OUTPUT_RETRIES
    ):
        ctx.filter_retry_count += 1
        run.on_log_entry(type("E", (), {
            "kind": "warning",
            "message": (
                f"output filter rejected the draft — revising "
                f"(attempt {ctx.filter_retry_count}/{constants.MAX_OUTPUT_RETRIES})"
            ),
            "detail": {},
        })())
        # hand the reason to the orchestrator and clear the block so stages re-run
        ctx.filter_feedback = ctx.filter_block_reason
        ctx.blocked = False
        ctx.filter_blocked = False
        ctx.filter_block_reason = None
        run.on_status("orchestrating")
        try:
            ports = build_default_ports(ctx)
            revised = await asyncio.wait_for(
                run_loop(ctx.normalized_input, ports, ctx),
                timeout=constants.ORCHESTRATOR_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 — surface as a run failure, never crash
            ctx.failed = True
            ctx.failure_error = exc
            return flow
        ctx.orchestrator_response = revised
        run.on_experts_settled(ctx.expert_calls)
        run.on_status("filtering")
        flow = await _OUTPUT_FILTER(flow)
        ctx = flow.ctx
    ctx.filter_feedback = None
    return flow


async def execute(run: RunState) -> None:
    """Drive the real pipeline for one run, emitting events as it goes."""
    flow: Flow[Any] = Flow.new(
        run.brief,
        session_id=run.session_id or run.id,
        user_id=run.user_id,
    )
    # observe the decision log without touching pipeline code
    flow.ctx.decision_log = _ObservedLog(run.on_log_entry)
    # replay this session's earlier turns as real chat history — the orchestrator
    # continues the conversation instead of re-reading a summary blob
    flow.ctx.conversation = _build_conversation(run)
    # the user's wiki — the highest-trust memory tier, loaded as text at hydration
    flow.ctx.wiki_entries = auth.fetch_wiki(run.user_id)

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

            # if the output filter rejected the draft, let the orchestrator revise
            # and retry (bounded, fail-closed) before we treat it as blocked
            if flow.ctx.filter_blocked:
                flow = await _recover_from_filter_block(flow, run)

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
                # record WHICH gate blocked so the UI can explain it accurately
                if ctx.sanitization_blocked:
                    run.block_stage = "sanitize"
                elif ctx.verifier_blocked:
                    run.block_stage = "verify"
                elif ctx.filter_blocked:
                    run.block_stage = "filter"
                else:
                    run.block_stage = "security"
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
