"""
Run execution + live streaming driver.

Calls core.pipeline's single stage-chain driver, observing status and decision-log
events without modifying pipeline code. Events mirror the frontend RunEvent union.

Owns per-run model overrides, session replay, and end-to-end API delivery.

Output-filter recovery stays in `core.pipeline` so CLI and web share one path;
this driver streams its narration and reads/writes the shared `RunState` via `STORE`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from foundation import Flow

from core import pipeline
from core.budget.context import budget_user_scope
from core.llm import model_overrides, usage_scope
from core.orchestrator.utils.decision_log import derive_record as _derive_decision_record

from observability import DecisionLogSink
import settings

from . import audit as _audit_trail, auth, config
from . import decision_audit as _decision_audit
from .run_inputs import gather_lineage_files, persist_inputs
from .run_sources import collect_sources as _collect_sources
from .run_state import RunState, TERMINAL_STATUSES, _now, _process_summary
from .run_store import STORE


def build_model_overrides(user_id: str, session: dict[str, str] | None = None) -> dict[str, str]:
    """Resolve run model overrides as role -> "provider:model".

    Per-session choices override stored workspace defaults. Only unlocked roles
    are honored; security gates (verifier and filter) are never overridable.
    """
    prefs = auth.model_prefs_get(user_id)
    merged = {**prefs, **(session or {})}   # the session choice overrides the workspace default
    return {
        role: config.qualify_model(model)
        for role, model in merged.items()
        if role in config.SELECTABLE_ROLES   # silently drop locked/unknown roles
    }


# Keep the whole session until this generous central bound; beyond it, condense only
# the oldest turns so recent context stays verbatim and growth remains bounded.
_HISTORY_CHAR_BUDGET = settings.BUDGET.history_char_budget


def _turn_assistant_content(turn: RunState) -> str:
    """A prior assistant turn: message/report with provenance, or an honest
    marker when nothing was delivered."""
    message = (turn.message or "").strip()
    report = (turn.report or "").strip()
    if report:
        body = f"{message}\n\n{report}" if message else report
        process = _process_summary(turn)
        if process and not process.startswith("No experts"):
            body += f"\n\n[How I produced this: {process}]"
        return body
    if message:
        return message
    note = {
        "blocked": "was stopped by the security pipeline and no answer was delivered",
        "failed": "did not complete due to a pipeline error",
    }.get(turn.status, "produced no answer")
    return f"[The previous turn {note}. Adjust and try again.]"


def _turn_user_content(turn: RunState) -> str:
    """One prior turn's user side: the brief, plus a note of any files it attached."""
    user_content = turn.brief
    names = [f.get("name", "file") for f in (turn.inputs or []) if isinstance(f, dict)]
    if names:
        user_content += f"\n[attached file(s) this turn: {', '.join(names)}]"
    return user_content


def _prior_turns(run: RunState) -> list[RunState]:
    """This run's effective turns strictly before it, oldest first."""
    return [
        t for t in STORE.effective_thread(run.user_id, run)
        if t.id != run.id and t.created_at < run.created_at
    ]


def _clip(text: str, limit: int) -> str:
    """Collapse whitespace and clip to `limit` chars with an ellipsis."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _recap_text(old: list[tuple[int, RunState]]) -> str:
    """A single condensed recap of the oldest turns that don't fit verbatim. They are
    summarized, NEVER dropped, and their full text stays retrievable via `recall`."""
    lines = [
        f"- Turn {n}: user asked “{_clip(_turn_user_content(t), 160)}”; "
        f"you replied “{_clip(_turn_assistant_content(t), 220)}”"
        for n, t in old
    ]
    return (
        f"[CONVERSATION RECAP — the earliest {len(old)} turn(s) of this session, condensed "
        "to save space (reference context, not a new request). The FULL text of any of them is "
        "still available: use your `recall` tool with a keyword to pull it back verbatim.]\n"
        + "\n".join(lines)
    )


# always keep at least this many of the most-recent turns verbatim, even mid-condense
# (config/backend/budget.yaml — one place to tune the whole product's budget knobs)
_VERBATIM_TURN_FLOOR = settings.BUDGET.verbatim_turn_floor


def _build_conversation(run: RunState) -> list[dict]:
    """Replay this session's earlier turns as neutral chat history (oldest first). Recent
    turns stay verbatim. Past `_HISTORY_CHAR_BUDGET`, oldest turns become a front-loaded
    recap; `recall` can still retrieve their full text from ctx.session_transcript (W8)."""
    # one (chars, [user_msg, assistant_msg], turn_number, turn) block per turn, oldest first
    blocks: list[tuple[int, list[dict], int, RunState]] = []
    for n, turn in enumerate(_prior_turns(run), start=1):
        msgs = [
            {"role": "user", "content": _turn_user_content(turn)},
            {"role": "assistant", "content": _turn_assistant_content(turn)},
        ]
        blocks.append((sum(len(m["content"]) for m in msgs), msgs, n, turn))
    # condense from the OLDEST until under budget, but always keep the most-recent turns whole
    total = sum(c for c, _, _, _ in blocks)
    condensed: list[tuple[int, RunState]] = []
    while total > _HISTORY_CHAR_BUDGET and len(blocks) > _VERBATIM_TURN_FLOOR:
        chars, _, n, turn = blocks.pop(0)
        total -= chars
        condensed.append((n, turn))
    out = [m for _, msgs, _, _ in blocks for m in msgs]
    if condensed and out:
        # fold the recap onto the first (user) message so history stays strictly alternating
        out[0] = {"role": "user", "content": _recap_text(condensed) + "\n\n" + out[0]["content"]}
    return out


def _build_transcript(run: RunState) -> list[dict]:
    """Full prior-turn transcript feeding `recall`, including turns condensed from
    visible history (W8)."""
    return [
        {"n": n, "user": _turn_user_content(turn), "assistant": _turn_assistant_content(turn)}
        for n, turn in enumerate(_prior_turns(run), start=1)
    ]


async def _gather_session_files(run: RunState, current: list | None) -> list:
    """Load current and effective-prior uploads through the lineage door."""
    return await gather_lineage_files(STORE, run, current)


async def execute(run: RunState, input_files: list | None = None) -> None:
    """Drive the real pipeline for one run, emitting events as it goes.

    Current scanned `input_files` join stored prior-session files for expert workspace
    seeding. The brief itself still crosses the full pipeline."""
    session_files: list = []
    ctx = None

    def _prepare(flow: Flow[Any]) -> None:
        """Seed the context the API owns, before any stage runs."""
        nonlocal ctx
        # Retain pipeline state through interruption so terminal audits use
        # authoritative expert/tool records instead of the presentation log.
        ctx = flow.ctx
        # Replay real history; condensed oldest turns remain available through the
        # full transcript used by `recall` (W8).
        flow.ctx.conversation = _build_conversation(run)
        flow.ctx.session_transcript = _build_transcript(run)
        # Project-scope the highest-trust wiki to prevent client bleed; learned Qdrant
        # tiers remain account-scoped pending the memory workstream.
        flow.ctx.wiki_entries = auth.fetch_wiki(run.user_id, run.project_id)
        # Seed all bounded session files so experts can read earlier uploads.
        flow.ctx.input_files = session_files

    def _on_stage(stage) -> None:
        """Before each stage: surface its coarse phase status (deduped — consecutive
        stages can share one status, so we only emit on a change)."""
        if stage.status != run.status:
            run.on_status(stage.status)

    def _on_stage_end(stage, flow: Flow[Any]) -> None:
        """After orchestration: reconcile expert states from ctx.expert_calls."""
        if stage.name == "orchestrator":
            run.on_experts_settled(flow.ctx.expert_calls)

    run_usage = None   # bound by usage_scope below; read in the except handlers too
    decision_log = DecisionLogSink(run.on_log_entry)
    try:
        # Runs become cancellable before this I/O starts: routes register this execute()
        # task immediately after STORE.create(), closing the create/cancel race even when
        # artifact persistence uses a genuinely asynchronous backend.
        await persist_inputs(run, input_files or [])
        session_files = await _gather_session_files(run, input_files)

        # user model preferences apply to every stage in this run. The pipeline is
        # the single end-to-end runner; the API only observes it (status, decision
        # log, expert reconciliation) and owns the classification + delivery. Output-
        # filter recovery lives INSIDE the pipeline now (one shared loop for CLI + web),
        # narrated on the decision log we already stream.
        # usage_scope meters the real tokens every LLM call in this turn spends, so
        # run.tokens_used (and the /usage aggregate) reflect actual spend, not 0.
        # budget_user_scope identifies this turn's spend for the retry.py enforcement anchor
        # (core/llm/retry.py) — inert while settings.BUDGET.enforcement_enabled is False.
        with (
            model_overrides(build_model_overrides(run.user_id, run.session_models)),
            usage_scope() as run_usage,
            budget_user_scope(run.user_id),
        ):
            flow: Flow[Any] = await pipeline.run(
                run.brief,
                session_id=run.session_id or run.id,
                user_id=run.user_id,
                # pin the trace to the run id so captured artifacts (stored under
                # ctx.trace_id) are addressable by the same id the API serves them under
                trace_id=run.id,
                # observe the decision log live without touching pipeline code
                decision_log=decision_log,
                prepare=_prepare,
                on_stage=_on_stage,
                on_stage_end=_on_stage_end,
            )

            # real metered tokens for this turn (every model call funnelled through
            # core.llm.run_agent within the scope above). Charged on every outcome —
            # delivered, blocked, or cancelled — since the models already ran.
            run.tokens_used = run_usage.total_tokens

            # reconcile the FINAL expert state: a filter-recovery revision re-runs the
            # reasoning without re-firing the orchestrator stage's on_stage_end, so
            # bring the expert panel up to date with whatever the accepted draft used.
            run.on_experts_settled(flow.ctx.expert_calls)

            ctx = flow.ctx
            _resp = ctx.orchestrator_response
            _presentation = getattr(_resp, "presentation", "report")
            if _presentation != "chat":
                # Preserve the report-mode conversational note. Live say() already
                # populated run.message; legacy direct producers use response.message.
                _final_msg = getattr(_resp, "message", "") if _resp is not None else ""
                if _final_msg and not run.message:
                    run.message = _final_msg
                    run.emit({"type": "message_delta", "text": _final_msg})

            # Honest completion: the orchestrator degrades rather than failing when the
            # loop cannot finish (wall-clock timeout, provider rate-limit storm, fault)
            # — it answers from what it already gathered. That answer is real and it is
            # delivered, so `status` stays `delivered`; but the run did NOT finish the
            # work, and saying only "delivered" reads as success. Surface the
            # orchestrator's OWN degraded metadata (core/orchestrator/utils/recovery.py
            # sets `degraded`/`cause`) so the UI can say "partial result, timed out"
            # without parsing the report prose for the reason string.
            #
            # Read after the pipeline returns, deliberately: the revision loop replaces
            # ctx.orchestrator_response when a revision SUCCEEDS, which correctly clears
            # the degraded marker — a run that recovered is not partial.
            if _resp is not None:
                _meta = getattr(_resp, "metadata", None) or {}
                if _meta.get("degraded"):
                    run.completion_state = "partial"
                    run.completion_reason = _meta.get("cause")

            # CB5 earned seal: surface the output filter's real verdict once it ran,
            # on BOTH the pass and block path — a block is itself a verdict. Stays
            # unemitted if an earlier gate (sanitize/verify) blocked before the
            # filter ever ran. Emitted once, right before the terminal status below.
            if ctx.filter_result is not None:
                run.on_verification(ctx.filter_result.groundedness)

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
                run.status = "blocked"
                # durable audit record — one per blocked run, scoped to owner.
                # The ENTIRE operation (gathering the fields AND the write) is guarded:
                # audit is best-effort and must never turn a blocked run into a failed
                # one, even if the flow is missing an expected field.
                try:
                    _block_origin = flow.meta.origin
                    _block_reason_text = (
                        ctx.sanitization_block_reason if ctx.sanitization_blocked else
                        ctx.verifier_block_reason if ctx.verifier_blocked else
                        ctx.filter_block_reason if ctx.filter_blocked else
                        None
                    )
                    _audit_trail.write_block_record(
                        user_id=ctx.user_id,
                        session_id=ctx.session_id,
                        trace_id=ctx.trace_id,
                        block_code=ctx.block_reason or "",
                        threat_level=flow.threat.value,
                        origin=_block_origin.value if _block_origin else "unknown",
                        reason=_block_reason_text,
                    )
                except Exception:  # noqa: BLE001 — audit is best-effort, never fatal
                    pass
            elif ctx.failed:
                if ctx.failure_error:
                    run.on_log_entry(
                        type("E", (), {
                            "kind": "error",
                            "message": str(ctx.failure_error)[:300],
                            "detail": {},
                        })()
                    )
                run.status = "failed"
            else:
                # The output filter's accepted text is canonical in both presentations.
                text = str(ctx.final_response) if ctx.final_response is not None else ""
                # surface the delivered output artifacts (experts captured them to
                # durable storage; here we just collect their refs for the API).
                # Only on the delivered path — a withheld draft keeps its files held.
                run.artifacts = [
                    art
                    for finding in ctx.expert_findings
                    for art in (finding.metadata or {}).get("artifacts", [])
                ]
                # Sources and artifacts do not decide presentation.
                _srcs = _collect_sources(ctx)
                run.sources = _srcs
                run.emit({"type": "sources", "sources": _srcs})
                if _presentation == "chat":
                    # A lone say() is a weak-model casual answer, not substantive work.
                    # Real work is authoritative only when Flow recorded a tool/expert call.
                    if not run.message or ctx.tool_calls or ctx.expert_calls:
                        separator = "\n\n" if run.message else ""
                        run.on_log_entry(
                            type(
                                "E",
                                (),
                                {"kind": "message", "message": f"{separator}{text}"},
                            )()
                        )
                else:
                    # Report contract: sources → report_delta×N → report_done → delivered.
                    await run.stream_report(text)
                run.status = "delivered"

    except asyncio.CancelledError:
        # the task was cancelled, which unwound the pipeline at its next await (no
        # output-filter delivery ran). Mark the run `cancelled` and let `finally`
        # finish the stream + persist — but only for a stop THIS server signalled
        # through RunStore.request_cancel (sets cancel_requested), which covers
        # both POST /runs/:id/cancel AND the lifespan shutdown drain (app.py's
        # shutdown loop calls request_cancel too, so an in-flight run at process
        # exit is honestly reported `cancelled`, not resurrected as something
        # else on the next boot). A CancelledError from anywhere ELSE (a bug, an
        # unrelated external cancel) did NOT go through request_cancel, so
        # cancel_requested is still False — re-raise instead of mislabeling it.
        if not run.cancel_requested:
            raise
        # charge the tokens spent up to the stop (completed model calls accumulated
        # before the cancel interrupted the in-flight one), per the usage-based model.
        if run_usage is not None:
            run.tokens_used = run_usage.total_tokens
        run.status = "cancelled"
    except Exception as exc:  # the web layer never lets a run take the server down
        if run_usage is not None:
            run.tokens_used = run_usage.total_tokens
        run.on_log_entry(
            type("E", (), {"kind": "error", "message": f"pipeline error: {exc}", "detail": {}})()
        )
        run.status = "failed"
    finally:
        # a run deleted mid-flight (its session was removed) must not be re-persisted
        # by this finally — that would resurrect the row the delete just removed.
        publish_terminal = run.status in TERMINAL_STATUSES and not run.deleted
        if publish_terminal:
            # CB4 institutional decision memory mirrors decisions captured before
            # EVERY terminal outcome. A crash/cancellation has no returned Flow, so
            # derive against a minimal context carrying the live observing sink.
            # Best-effort: mirror failure cannot change run outcome or reach client.
            try:
                audit_ctx = ctx or Flow.new(
                    run.brief,
                    session_id=run.session_id or run.id,
                    user_id=run.user_id,
                    trace_id=run.id,
                ).ctx
                audit_log = audit_ctx.decision_log if ctx is not None else decision_log
                audit_ctx.decision_log = audit_log
                _decision_records = [
                    record
                    for entry in audit_log
                    if (record := _derive_decision_record(entry, audit_ctx)) is not None
                ]
                _decision_audit.write_decision_records(
                    user_id=audit_ctx.user_id,
                    session_id=audit_ctx.session_id,
                    trace_id=audit_ctx.trace_id,
                    records=_decision_records,
                )
            except Exception:  # noqa: BLE001 — decision-mirror write is best-effort
                pass
            try:
                # Durability precedes terminal publication: a client must never be
                # told delivery completed when final state failed to commit.
                STORE.persist(run)
            except Exception as exc:  # noqa: BLE001 — convert storage fault honestly
                run.status = "failed"
                run.on_log_entry(
                    type("E", (), {
                        "kind": "error",
                        "message": f"final persistence failed ({type(exc).__name__})",
                        "detail": {},
                    })()
                )
            run.emit({"type": "status", "status": run.status})
        run.emit({"type": "message_done"})   # close the conversational channel for this turn
        run.finish()
