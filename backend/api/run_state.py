"""
The pure run record + its serialization + live event mappers.

`RunState` is the in-memory record of one run/turn: its status, buffered events
(for SSE replay), decision log, expert states, report, artifacts, inputs, and the
session/feedback metadata. It also owns the mappers that turn pipeline objects
(decision-log entries, settled expert calls) into the frontend RunEvent shapes,
and the REST serializers (`summary_json`/`full_json`). It carries no pipeline or
persistence dependencies — those live in `run_store` (persistence) and
`run_driver` (execution).
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_REPORT_CHUNK_WORDS = 6

# The statuses a run can END in — no further events will arrive. Shared by the SSE
# transport (when to short-circuit a reconnect) and the cancel path (when a cancel
# is an idempotent no-op). `cancelled` is the user-initiated stop, distinct from
# `failed` (a system error) and `blocked` (a security gate).
TERMINAL_STATUSES = frozenset({"delivered", "blocked", "failed", "cancelled"})


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
    # the orchestrator's conversational message for this turn (the chat bubble), built
    # live from `message_delta` events. Distinct from `report` (the deliverable). A turn
    # may have a message and no report (pure conversation), both, or report only.
    message: str | None = None
    tokens_used: int = 0
    # delivered output artifacts (ArtifactRef dicts) — files an expert produced
    # and published, captured out of its workspace to durable storage
    artifacts: list[dict] = field(default_factory=list)
    # uploaded input files admitted for this run (metadata only: name/modality/size;
    # the bytes are passed to execute() and seeded into the expert workspace, never stored here)
    inputs: list[dict] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    # live execution handle, set by the route right after the run's task is created;
    # used to cooperatively cancel an in-flight run. Runtime-only — never persisted
    # (excluded from repr/compare; the store writes explicit columns, not the object).
    task: Any | None = field(default=None, repr=False, compare=False)
    # set when the user requests cancellation, so the execute() coroutine can tell a
    # user cancel apart from any other CancelledError (e.g. server shutdown).
    cancel_requested: bool = False
    # set when this run's session is deleted mid-flight, so execute()'s finally skips
    # persisting it (which would resurrect the row the delete just removed).
    deleted: bool = False
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
    # the project (client / body of work) this run belongs to, or None for an
    # unscoped run. Follow-ups inherit the parent's project.
    project_id: str | None = None
    # per-session model choices for THIS run (role -> bare model id), layered over
    # the user's workspace defaults at execute time. Empty = use workspace defaults.
    session_models: dict[str, str] = field(default_factory=dict)

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
        kind = getattr(entry, "kind", "observation")
        if kind == "message":
            # the orchestrator's conversational voice: a SEPARATE channel from the
            # structured decision log. Stream it as a message_delta and accumulate the
            # turn's chat bubble; it does not go into the decision log.
            text = str(getattr(entry, "message", ""))
            if text:
                self.message = (self.message or "") + text
                self.emit({"type": "message_delta", "text": text})
            return
        mapped = {
            "id": f"log_{secrets.token_hex(6)}",
            "ts": _now(),
            "kind": kind,
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
            "projectId": self.project_id,
        }

    def full_json(self) -> dict:
        return {
            **self.summary_json(),
            "brief": self.brief,
            "decisionLog": self.log,
            "experts": list(self.experts.values()),
            "message": self.message,   # the conversational chat bubble (separate from report)
            "report": self.report,
            "sources": [],  # structured sources arrive with the citation expert
            "artifacts": self.artifacts,
            "inputs": self.inputs,
            "feedbackRating": self.feedback_rating,
            "feedbackComment": self.feedback_comment,
            "parentRunId": self.parent_run_id,
            "sessionId": self.session_id or self.id,
            "blockStage": self.block_stage,
        }
