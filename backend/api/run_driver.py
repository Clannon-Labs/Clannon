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
  - `_recover_from_filter_block` — bounded, fail-closed output-filter recovery.
  - `execute` — drive one run end-to-end, emit events, classify + persist.

It reads/writes runs through the shared `STORE` and the `RunState` record.
"""

from __future__ import annotations

import asyncio
from typing import Any

from foundation import Flow, constants

from core import pipeline
from core.llm import model_overrides
from security.filter import run as _OUTPUT_FILTER

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
        # log, expert reconciliation) and owns the post-run recovery + classification.
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

    except Exception as exc:  # the web layer never lets a run take the server down
        run.on_log_entry(
            type("E", (), {"kind": "error", "message": f"pipeline error: {exc}", "detail": {}})()
        )
        run.on_status("failed")
    finally:
        run.finish()
        STORE.persist(run)
