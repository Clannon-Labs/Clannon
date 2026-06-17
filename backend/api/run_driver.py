"""
Run execution + live streaming driver.

Drives the same stage chain as core.pipeline (imported, not duplicated) but steps
it stage-by-stage so the web layer can emit status transitions, and swaps
ctx.decision_log for an observing list so every DecisionLogEntry the orchestrator
emits is pushed to subscribers the moment it lands — no pipeline code is modified.
Event shapes mirror the frontend RunEvent union exactly.

This module owns:
  - `build_model_overrides` — resolve per-run model overrides (workspace + session).
  - `_build_conversation` — replay a session's earlier turns as chat history.
  - `execute` — drive one run end-to-end, emit events, classify + persist.

Output-filter recovery is NOT here: it's the single shared `recover_from_filter_block`
in `core.pipeline`, run inside `pipeline.run` for both the CLI and the web path and
narrated on the decision log this driver already streams.

It reads/writes runs through the shared `STORE` and the `RunState` record.
"""

from __future__ import annotations

import asyncio
from typing import Any

from foundation import Flow

from core import pipeline
from core.llm import model_overrides

from observability import DecisionLogSink

from . import auth, config
from .run_state import RunState, _now, _process_summary
from .run_store import STORE


def build_model_overrides(user_id: str, session: dict[str, str] | None = None) -> dict[str, str]:
    """
    Resolve the model overrides for a run, as role -> "provider:model".

    Two layers: the user's stored WORKSPACE defaults (per-role, persisted via
    /settings/models), with the run's PER-SESSION choices (`session`, role -> bare
    model id) layered on top — the session choice wins for that run. Only unlocked
    roles are honored; locked security gates (verifier, filter) are never overridable.
    """
    prefs = auth.model_prefs_get(user_id)
    merged = {**prefs, **(session or {})}   # the session choice overrides the workspace default
    return {
        role: config.qualify_model(model)
        for role, model in merged.items()
        if role in config.SELECTABLE_ROLES   # silently drop locked/unknown roles
    }


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


async def execute(run: RunState, input_files: list | None = None) -> None:
    """Drive the real pipeline for one run, emitting events as it goes.

    `input_files` are uploaded, already-malware-scanned foundation.InputFile objects
    (admitted at the HTTP boundary); they ride on the context and are seeded into a
    file-capable expert's workspace. The brief itself still crosses the full pipeline."""
    def _prepare(flow: Flow[Any]) -> None:
        """Seed the context the API owns, before any stage runs."""
        # replay this session's earlier turns as real chat history — the orchestrator
        # continues the conversation instead of re-reading a summary blob
        flow.ctx.conversation = _build_conversation(run)
        # the user's wiki — the highest-trust memory tier, loaded as text at hydration
        flow.ctx.wiki_entries = auth.fetch_wiki(run.user_id)
        # uploaded input files for this run — seeded into the expert workspace downstream
        flow.ctx.input_files = input_files or []

    def _on_stage(stage) -> None:
        """Before each stage: surface its coarse phase status (deduped — consecutive
        stages can share one status, so we only emit on a change)."""
        if stage.status != run.status:
            run.on_status(stage.status)

    def _on_stage_end(stage, flow: Flow[Any]) -> None:
        """After orchestration: reconcile expert states from ctx.expert_calls."""
        if stage.name == "orchestrator":
            run.on_experts_settled(flow.ctx.expert_calls)

    try:
        # user model preferences apply to every stage in this run. The pipeline is
        # the single end-to-end runner; the API only observes it (status, decision
        # log, expert reconciliation) and owns the classification + delivery. Output-
        # filter recovery lives INSIDE the pipeline now (one shared loop for CLI + web),
        # narrated on the decision log we already stream.
        with model_overrides(build_model_overrides(run.user_id, run.session_models)):
            flow: Flow[Any] = await pipeline.run(
                run.brief,
                session_id=run.session_id or run.id,
                user_id=run.user_id,
                # pin the trace to the run id so captured artifacts (stored under
                # ctx.trace_id) are addressable by the same id the API serves them under
                trace_id=run.id,
                # observe the decision log live without touching pipeline code
                decision_log=DecisionLogSink(run.on_log_entry),
                prepare=_prepare,
                on_stage=_on_stage,
                on_stage_end=_on_stage_end,
            )

            # reconcile the FINAL expert state: a filter-recovery revision re-runs the
            # reasoning without re-firing the orchestrator stage's on_stage_end, so
            # bring the expert panel up to date with whatever the accepted draft used.
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
                # surface the delivered output artifacts (experts captured them to
                # durable storage; here we just collect their refs for the API).
                # Only on the delivered path — a withheld draft keeps its files held.
                run.artifacts = [
                    art
                    for finding in ctx.expert_findings
                    for art in (finding.metadata or {}).get("artifacts", [])
                ]
                run.on_status("delivered")
                await run.stream_report(str(text))

    except asyncio.CancelledError:
        # cooperative cancel via POST /runs/:id/cancel: the task was cancelled, which
        # unwound the pipeline at its next await (no output-filter delivery ran). Mark
        # the run `cancelled` and let `finally` finish the stream + persist. Only honor
        # a cancel the USER asked for — any other CancelledError (e.g. server shutdown)
        # is not a user stop, so re-raise it instead of mislabeling the run.
        if not run.cancel_requested:
            raise
        run.on_status("cancelled")
    except Exception as exc:  # the web layer never lets a run take the server down
        run.on_log_entry(
            type("E", (), {"kind": "error", "message": f"pipeline error: {exc}", "detail": {}})()
        )
        run.on_status("failed")
    finally:
        run.finish()
        STORE.persist(run)
