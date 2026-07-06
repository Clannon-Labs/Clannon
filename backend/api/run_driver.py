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
from urllib.parse import urlparse

from foundation import Flow, InputFile

from core import pipeline
from core.artifacts import LocalArtifactStore
from core.llm import model_overrides, usage_scope

from observability import DecisionLogSink
import settings

from . import audit as _audit_trail, auth, config
from .run_state import RunState, _now, _process_summary
from .run_store import STORE, INPUT_NS


def _collect_sources(ctx) -> list[dict]:
    """Collect de-duplicated grounded-search source URLs from all tool call records
    (orchestrator direct calls + every expert's sub-tool calls), mapped to the Source
    shape the frontend expects: {id, title, url, domain}. Only records that carry a
    `sources` list in their result are considered — this is the field web_search returns.
    Never raises: a malformed URL or unexpected result shape is skipped silently."""
    seen: set[str] = set()
    sources: list[dict] = []
    all_records = list(ctx.tool_calls)
    for expert in ctx.expert_calls:
        all_records.extend(expert.sub_tool_calls)
    for record in all_records:
        if not record.success or not isinstance(record.result, dict):
            continue
        url_list = record.result.get("sources")
        if not isinstance(url_list, list):
            continue
        for url in url_list:
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            try:
                parsed = urlparse(url)
                netloc = parsed.netloc or ""
                domain = netloc[4:] if netloc.startswith("www.") else netloc
                path = parsed.path.rstrip("/")
                slug = path.split("/")[-1].replace("-", " ").replace("_", " ").strip() if path else ""
                title = f"{domain} — {slug}" if slug else domain
            except Exception:  # noqa: BLE001
                domain = ""
                title = url
            sources.append({
                "id": f"src_{len(sources) + 1}",
                "title": title or url,
                "url": url,
                "domain": domain,
            })
    return sources


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


# The WHOLE session travels as chat history — the orchestrator should see everything
# that happened. We only trim when a session grows genuinely huge, and then we drop the
# OLDEST turns (keeping the recent ones whole), bounded by this character budget so the
# context stays complete without growing without limit. Generous on purpose. Sourced from
# the central control panel (config/backend/budget.yaml) so it's tunable without a code edit.
_HISTORY_CHAR_BUDGET = settings.BUDGET.history_char_budget


def _turn_assistant_content(turn: RunState) -> str:
    """One prior turn's assistant side, as the model should re-read it: the
    conversational message AND/OR the delivered report (with a provenance note), or an
    honest marker if the turn produced nothing."""
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
    """This session's turns strictly BEFORE this one, oldest first."""
    session = run.session_id or run.id
    return [
        t for t in STORE.session_turns(run.user_id, session)
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
    turns are kept VERBATIM (user brief + assistant message/report). When a session grows
    past `_HISTORY_CHAR_BUDGET`, the oldest turns are NOT dropped — they are CONDENSED into a
    recap folded onto the front of the kept history (so the model still knows they happened
    and their gist), and their full text stays retrievable via the `recall` tool /
    ctx.session_transcript (W8)."""
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
    """The FULL, untrimmed transcript of this session's earlier turns (oldest first): one
    {n, user, assistant} record per prior turn, verbatim. Feeds ctx.session_transcript so the
    orchestrator's `recall` tool can return ANY earlier turn in full, even one the visible
    history condensed (W8)."""
    return [
        {"n": n, "user": _turn_user_content(turn), "assistant": _turn_assistant_content(turn)}
        for n, turn in enumerate(_prior_turns(run), start=1)
    ]


# Bounds on re-seeding a whole session's uploaded files, so a long session can't seed
# unbounded data into the workspace.
_MAX_SESSION_FILES = 30
_MAX_SESSION_FILE_BYTES = 64 * 1024 * 1024
# inputs are persisted under a namespace distinct from a run's OUTPUT artifacts, so the
# two never collide and inputs are never served by the artifact download route.
def _input_ns(run_id: str) -> str:
    return f"{INPUT_NS}{run_id}"


async def persist_inputs(run: RunState, input_files: list) -> None:
    """Persist a turn's uploaded files (already malware-scanned) so LATER turns in the
    session can re-read them, and record their store refs on `run.inputs`. Best-effort:
    a file that fails to store is still admitted for THIS turn (it rides `input_files`),
    it just won't survive to a follow-up."""
    store = LocalArtifactStore()
    entries: list[dict] = []
    for f in input_files:
        meta = f.as_dict()
        try:
            meta["id"] = (await store.put(_input_ns(run.id), f.name, f.data)).id
        except Exception:  # noqa: BLE001 — storage hiccup must not fail the run
            pass
        entries.append(meta)
    run.inputs = entries


async def _gather_session_files(run: RunState, current: list | None) -> list:
    """Every file uploaded across THIS session, so the orchestrator can read a file from
    an earlier turn: the current turn's files (already in memory) plus prior turns'
    persisted files, loaded from the store. Bounded by file count and total bytes; a
    missing/unreadable prior file is skipped, never fatal."""
    files = list(current or [])
    seen = {getattr(f, "name", "") for f in files}
    total = sum(int(getattr(f, "size", 0) or 0) for f in files)
    store = LocalArtifactStore()
    for turn in STORE.session_turns(run.user_id, run.session_id or run.id):
        if turn.id == run.id or turn.created_at >= run.created_at:
            continue
        for meta in (turn.inputs or []):
            if not isinstance(meta, dict):
                continue
            name, aid = meta.get("name"), meta.get("id")
            if not name or not aid or name in seen:
                continue
            if len(files) >= _MAX_SESSION_FILES or total >= _MAX_SESSION_FILE_BYTES:
                return files
            try:
                data = await store.get(aid)
            except Exception:  # noqa: BLE001
                continue
            files.append(InputFile(
                name=name, modality=meta.get("modality", "text"), data=data, size=len(data),
            ))
            seen.add(name)
            total += len(data)
    return files


async def execute(run: RunState, input_files: list | None = None) -> None:
    """Drive the real pipeline for one run, emitting events as it goes.

    `input_files` are this turn's uploaded, already-malware-scanned foundation.InputFile
    objects. They are combined with the files uploaded EARLIER in the session (re-loaded
    from the store) so the orchestrator can read any file from any turn, then seeded into
    a file-capable expert's workspace. The brief itself still crosses the full pipeline."""
    session_files = await _gather_session_files(run, input_files)

    def _prepare(flow: Flow[Any]) -> None:
        """Seed the context the API owns, before any stage runs."""
        # replay this session's earlier turns as real chat history — the orchestrator
        # continues the conversation instead of re-reading a summary blob. A long session's
        # oldest turns are condensed (not dropped); the full untrimmed transcript rides
        # alongside so the `recall` tool can pull any earlier turn back verbatim (W8).
        flow.ctx.conversation = _build_conversation(run)
        flow.ctx.session_transcript = _build_transcript(run)
        # the user's wiki — the highest-trust memory tier, loaded as text at hydration.
        # Scoped to the run's project so a client's wiki doesn't bleed across projects;
        # account-wide when the run has no project. (The learned Qdrant tiers are still
        # account-scoped — project-scoping those is the memory workstream's.)
        flow.ctx.wiki_entries = auth.fetch_wiki(run.user_id, run.project_id)
        # every file uploaded this SESSION (this turn + earlier turns), seeded into the
        # expert workspace downstream so a file from an earlier message is still readable
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
    try:
        # user model preferences apply to every stage in this run. The pipeline is
        # the single end-to-end runner; the API only observes it (status, decision
        # log, expert reconciliation) and owns the classification + delivery. Output-
        # filter recovery lives INSIDE the pipeline now (one shared loop for CLI + web),
        # narrated on the decision log we already stream.
        # usage_scope meters the real tokens every LLM call in this turn spends, so
        # run.tokens_used (and the /usage aggregate) reflect actual spend, not 0.
        with model_overrides(build_model_overrides(run.user_id, run.session_models)), usage_scope() as run_usage:
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

            # real metered tokens for this turn (every model call funnelled through
            # core.llm.run_agent within the scope above). Charged on every outcome —
            # delivered, blocked, or cancelled — since the models already ran.
            run.tokens_used = run_usage.total_tokens

            # reconcile the FINAL expert state: a filter-recovery revision re-runs the
            # reasoning without re-firing the orchestrator stage's on_stage_end, so
            # bring the expert panel up to date with whatever the accepted draft used.
            run.on_experts_settled(flow.ctx.expert_calls)

            ctx = flow.ctx
            # The conversational message (chat bubble). If the orchestrator streamed it
            # live via say(), run.message is already built from message_delta events. If
            # instead it returned its reply as the final answer (a direct turn that didn't
            # call say()), surface that now so the bubble still shows + replays.
            _resp = ctx.orchestrator_response
            _final_msg = getattr(_resp, "message", "") if _resp is not None else ""
            if _final_msg and not run.message:
                run.message = _final_msg
                run.emit({"type": "message_delta", "text": _final_msg})

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
                run.on_status("failed")
            else:
                text = ctx.final_response or (
                    ctx.orchestrator_response.text if ctx.orchestrator_response else ""
                )
                # memory is persisted ONLY on the delivered path (post-filter), so the
                # /memory view is populated ONLY here. A blocked or failed draft wrote
                # nothing to memory, and its proposals (e.g. an in-flight `remember`) must
                # not appear in the view — run.memory_writes stays its empty default.
                # Surface the PERSISTED set (what the Manager actually wrote), never the
                # proposals: a proposal the write policy dropped is not a real memory.
                run.memory_writes = [
                    {
                        "content": getattr(w, "content", str(w)),
                        "rationale": getattr(w, "rationale", ""),
                        "ts": _now(),
                    }
                    for w in ctx.memory_writes_persisted
                ]
                # surface the delivered output artifacts (experts captured them to
                # durable storage; here we just collect their refs for the API).
                # Only on the delivered path — a withheld draft keeps its files held.
                run.artifacts = [
                    art
                    for finding in ctx.expert_findings
                    for art in (finding.metadata or {}).get("artifacts", [])
                ]
                # Collect grounded-search source URLs from all tool call records
                # (orchestrator direct + expert sub-calls), de-dup, and surface them as
                # the {type:"sources"} SSE frame BEFORE the report text streams.
                _srcs = _collect_sources(ctx)
                run.sources = _srcs
                run.emit({"type": "sources", "sources": _srcs})
                # Contract order (api/README.md /runs/:id/stream): the report streams
                # FIRST, the terminal status comes LAST — sources → report_delta×N →
                # report_done → status:delivered. Flipping the status earlier painted a
                # DELIVERED badge over a still-streaming report in the UI (frontend pins
                # the moment to the terminal status event).
                await run.stream_report(str(text))
                run.on_status("delivered")

    except asyncio.CancelledError:
        # cooperative cancel via POST /runs/:id/cancel: the task was cancelled, which
        # unwound the pipeline at its next await (no output-filter delivery ran). Mark
        # the run `cancelled` and let `finally` finish the stream + persist. Only honor
        # a cancel the USER asked for — any other CancelledError (e.g. server shutdown)
        # is not a user stop, so re-raise it instead of mislabeling the run.
        if not run.cancel_requested:
            raise
        # charge the tokens spent up to the stop (completed model calls accumulated
        # before the cancel interrupted the in-flight one), per the usage-based model.
        if run_usage is not None:
            run.tokens_used = run_usage.total_tokens
        run.on_status("cancelled")
    except Exception as exc:  # the web layer never lets a run take the server down
        if run_usage is not None:
            run.tokens_used = run_usage.total_tokens
        run.on_log_entry(
            type("E", (), {"kind": "error", "message": f"pipeline error: {exc}", "detail": {}})()
        )
        run.on_status("failed")
    finally:
        run.emit({"type": "message_done"})   # close the conversational channel for this turn
        run.finish()
        # a run deleted mid-flight (its session was removed) must not be re-persisted
        # by this finally — that would resurrect the row the delete just removed.
        if not run.deleted:
            STORE.persist(run)
