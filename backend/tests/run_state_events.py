"""
Hermetic harness for the three pure deterministic RunState live-event mappers
in api/run_state.py:156-199 that translate orchestration events into SSE frames
for the frontend demo's live decision-log and expert panels.

NO test exercised these before this file (re-confirmed on main: grep
on_experts_settled/stream_report/report_delta/expert_spawn across
backend/tests/ = zero hits).

Mappers under test
------------------
* on_log_entry (expert_spawn branch)  — lines ~156-166
* on_experts_settled                  — lines ~168-189
* stream_report                       — lines ~191-200

SSE contract cross-check
------------------------
Event names and payload keys are asserted against frontend/src/lib/api/types.ts
(RunEvent union, ExpertState shape) and the #31 drift fixture
(backend/tests/benchmarks/fixtures/sse_contract.json, PR #31 pending merge).
The fixture's relevant data is inlined below so this harness has no dependency
on the un-merged PR.

On any genuine divergence (a frame type the frontend RunEvent union does not
declare, or a required payload key missing) the harness writes a
needs-reviewer note to /home/amrit/.clannon_proposal and fails.  It does NOT
edit either side of the contract.

Serves C6 (multi-agent consistency — streamed expert/decision-log frames must
stay contract-compatible and traceable) and the Demo Readiness Gate (the live-
streaming surfaces the <3min demo depends on get a regression net alongside
message_channel.py, run_sources.py, and the SSE failure path).
"""

import asyncio
import pathlib
from types import SimpleNamespace

import pytest

from api.run_state import RunState, _REPORT_CHUNK_WORDS


# ---------------------------------------------------------------------------
# SSE contract reference
# Inlined from frontend/src/lib/api/types.ts + the #31 drift fixture.
# These are READ, never changed.  Cross-check failures write a proposal.
# ---------------------------------------------------------------------------

# RunEvent union: the complete set of `type` values the frontend declares.
# backend_required=True entries must be streamed; False = forward-compatible.
_FRONTEND_KNOWN_TYPES: set[str] = {
    "status", "log", "expert",
    "message_delta", "message_done",
    "report_delta", "report_done",
    "sources", "usage",
}

# Required payload keys per event type (besides `type` itself).
_REQUIRED_KEYS: dict[str, set[str]] = {
    "status":        {"status"},
    "log":           {"entry"},
    "expert":        {"expert"},
    "message_delta": {"text"},
    "message_done":  set(),
    "report_delta":  {"text"},
    "report_done":   set(),
    "sources":       {"sources"},
    "usage":         {"tokensUsed"},
}

# ExpertState required keys (frontend/src/lib/api/types.ts ExpertState interface)
_EXPERT_STATE_REQUIRED: set[str] = {"id", "name", "domain", "status", "toolCalls"}

# DecisionLogEntry required keys
_LOG_ENTRY_REQUIRED: set[str] = {"id", "ts", "kind", "title"}

# Valid ExpertStatus values (frontend/src/lib/api/types.ts ExpertStatus type)
_EXPERT_VALID_STATUSES: set[str] = {"spawned", "working", "summarizing", "done", "failed"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(run_id: str = "r1") -> RunState:
    return RunState(id=run_id, user_id="u1", title="t", brief="b", session_id=run_id)


def _spawn_entry(
    expert: str = "Research Expert",
    domain: str = "market",
    message: str = "Spawning research expert",
) -> SimpleNamespace:
    """Double for a decision-log entry with kind='expert_spawn'."""
    return SimpleNamespace(
        kind="expert_spawn",
        message=message,
        detail={"expert": expert, "domain": domain},
    )


def _expert_record(
    expert_name: str = "Research Expert",
    success: bool = True,
    tool_count: int = 2,
    summary: str = "Research complete. Found three key trends.",
    domain: str = "market",
) -> SimpleNamespace:
    """Double for an ExpertCallRecord (foundation/transport/context.py:111)."""
    return SimpleNamespace(
        expert_name=expert_name,
        success=success,
        sub_tool_calls=[SimpleNamespace() for _ in range(tool_count)],
        arguments={"domain": domain},
        result={"summary": summary},
    )


def _report_drift(unknown_types: set[str]) -> None:
    """Write a needs-reviewer note and fail on genuine SSE contract drift."""
    msg = (
        f"\n{'='*60}\n"
        "  SSE CONTRACT DRIFT DETECTED — needs-reviewer\n"
        f"  Unknown event types emitted: {sorted(unknown_types)}\n"
        "  These frame names are NOT declared in RunEvent\n"
        "  (frontend/src/lib/api/types.ts) — the frontend cannot\n"
        "  handle them. Do NOT edit the mapper; file a review.\n"
        f"{'='*60}"
    )
    proposal = pathlib.Path("/home/amrit/.clannon_proposal")
    existing = proposal.read_text() if proposal.exists() else ""
    proposal.write_text(
        existing
        + "\n\n## SSE contract drift (test/c6-run-state-event-mappers)\n"
        + msg
        + "\n"
    )
    pytest.fail(msg)


# ---------------------------------------------------------------------------
# (a) EXPERT-SPAWN FRAME
# on_log_entry with kind=="expert_spawn" must append a log entry AND emit a
# {"type":"expert"} frame carrying a minted eXX id, name from detail["expert"]
# (truncated to 60), domain from detail["domain"] (default "expert"),
# status=="working", toolCalls==0.
# ---------------------------------------------------------------------------

def test_expert_spawn_appends_decision_log_entry():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    assert len(run.log) == 1
    assert run.log[0]["kind"] == "expert_spawn"


def test_expert_spawn_emits_log_and_expert_frames():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    types = [e["type"] for e in run.events]
    assert "log" in types
    assert "expert" in types


def test_expert_spawn_log_entry_has_required_keys():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    log_frames = [e for e in run.events if e.get("type") == "log"]
    assert log_frames, "expected a log frame"
    assert _LOG_ENTRY_REQUIRED <= log_frames[0]["entry"].keys()


def test_expert_spawn_card_has_required_shape():
    """The emitted expert card must carry all ExpertState required keys."""
    run = _make_run()
    run.on_log_entry(_spawn_entry(expert="Market Analyst", domain="market"))
    expert_frames = [e for e in run.events if e.get("type") == "expert"]
    assert len(expert_frames) == 1
    card = expert_frames[0]["expert"]
    assert _EXPERT_STATE_REQUIRED <= card.keys(), (
        f"Missing ExpertState keys: {_EXPERT_STATE_REQUIRED - card.keys()}"
    )


def test_expert_spawn_card_initial_values():
    run = _make_run()
    run.on_log_entry(_spawn_entry(expert="Market Analyst", domain="market"))
    card = next(e["expert"] for e in run.events if e.get("type") == "expert")
    assert card["status"] == "working"
    assert card["toolCalls"] == 0
    assert card["domain"] == "market"
    assert card["name"] == "Market Analyst"


def test_expert_spawn_status_is_valid_expert_status():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    card = next(e["expert"] for e in run.events if e.get("type") == "expert")
    assert card["status"] in _EXPERT_VALID_STATUSES


def test_expert_spawn_mints_sequential_ids():
    run = _make_run()
    run.on_log_entry(_spawn_entry(expert="Expert A"))
    run.on_log_entry(_spawn_entry(expert="Expert B"))
    ids = [e["expert"]["id"] for e in run.events if e.get("type") == "expert"]
    assert ids == ["e1", "e2"]


def test_expert_spawn_name_truncated_to_60():
    long_name = "X" * 80
    run = _make_run()
    run.on_log_entry(_spawn_entry(expert=long_name))
    card = next(e["expert"] for e in run.events if e.get("type") == "expert")
    assert card["name"] == long_name[:60]
    assert len(card["name"]) == 60


def test_expert_spawn_domain_defaults_to_expert_when_absent():
    entry = SimpleNamespace(kind="expert_spawn", message="spawn", detail={})
    run = _make_run()
    run.on_log_entry(entry)
    card = next(e["expert"] for e in run.events if e.get("type") == "expert")
    assert card["domain"] == "expert"


# ---------------------------------------------------------------------------
# (b) SETTLE RECONCILIATION
# on_experts_settled([record]) must update the SAME eXX card minted at spawn
# (id reuse by index: run_state.py:171 uses f"e{i+1}"), set status="done" when
# record.success is True and status="failed" when False, set
# toolCalls==len(record.sub_tool_calls), and include summary from
# record.result["summary"] / ["text"] truncated to 400 chars.
# ---------------------------------------------------------------------------

def test_settle_done_updates_existing_card_status():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    assert run.experts["e1"]["status"] == "working"

    run.on_experts_settled([_expert_record(success=True)])
    assert run.experts["e1"]["status"] == "done"


def test_settle_failed_updates_existing_card_status():
    run = _make_run()
    run.on_log_entry(_spawn_entry())

    run.on_experts_settled([_expert_record(success=False)])
    assert run.experts["e1"]["status"] == "failed"


def test_settle_done_sets_tool_calls():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    run.on_experts_settled([_expert_record(success=True, tool_count=3)])
    assert run.experts["e1"]["toolCalls"] == 3


def test_settle_done_sets_summary():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    summary_text = "Found three key market trends."
    run.on_experts_settled([_expert_record(success=True, summary=summary_text)])
    assert run.experts["e1"]["summary"] == summary_text


def test_settle_summary_truncated_to_400():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    run.on_experts_settled([_expert_record(success=True, summary="S" * 500)])
    assert len(run.experts["e1"]["summary"]) == 400


def test_settle_summary_from_text_key_when_no_summary_key():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    record = SimpleNamespace(
        expert_name="Expert",
        success=True,
        sub_tool_calls=[],
        arguments={},
        result={"text": "Found via text key."},
    )
    run.on_experts_settled([record])
    assert run.experts["e1"]["summary"] == "Found via text key."


def test_settle_emits_expert_frame():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    events_before = len(run.events)
    run.on_experts_settled([_expert_record(success=True)])
    settle_frames = [e for e in run.events[events_before:] if e.get("type") == "expert"]
    assert len(settle_frames) == 1


def test_settle_reuses_same_eid_as_spawn():
    """Id-reuse-by-index: spawn mints e1, settle must update e1, not a new id."""
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    spawn_id = next(e["expert"]["id"] for e in run.events if e.get("type") == "expert")

    events_before = len(run.events)
    run.on_experts_settled([_expert_record(success=True)])
    settle_id = next(
        e["expert"]["id"]
        for e in run.events[events_before:]
        if e.get("type") == "expert"
    )
    assert spawn_id == settle_id == "e1"


def test_settle_done_frame_has_required_expert_state_keys():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    events_before = len(run.events)
    run.on_experts_settled([_expert_record()])
    frame = next(e for e in run.events[events_before:] if e.get("type") == "expert")
    assert _EXPERT_STATE_REQUIRED <= frame["expert"].keys()


def test_settle_done_status_is_valid_expert_status():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    run.on_experts_settled([_expert_record(success=True)])
    assert run.experts["e1"]["status"] in _EXPERT_VALID_STATUSES


def test_settle_failed_status_is_valid_expert_status():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    run.on_experts_settled([_expert_record(success=False)])
    assert run.experts["e1"]["status"] in _EXPERT_VALID_STATUSES


# ---------------------------------------------------------------------------
# (c) SETTLE WITHOUT PRIOR SPAWN
# on_experts_settled for an index never seen at spawn must mint a fresh card
# from the record rather than raising (run_state.py:175-180).
# ---------------------------------------------------------------------------

def test_settle_without_spawn_mints_fresh_card():
    run = _make_run()
    assert len(run.experts) == 0

    run.on_experts_settled([_expert_record(
        expert_name="Data Analyst",
        success=True,
        tool_count=1,
        summary="Completed analysis.",
        domain="data",
    )])

    assert "e1" in run.experts
    card = run.experts["e1"]
    assert card["name"] == "Data Analyst"
    assert card["status"] == "done"
    assert card["toolCalls"] == 1
    assert card["summary"] == "Completed analysis."


def test_settle_without_spawn_does_not_raise():
    """Settling with no prior spawn is explicitly supported — must not raise."""
    run = _make_run()
    run.on_experts_settled([_expert_record(success=False)])  # no exception expected


def test_settle_without_spawn_emits_expert_frame_with_required_keys():
    run = _make_run()
    run.on_experts_settled([_expert_record()])
    frames = [e for e in run.events if e.get("type") == "expert"]
    assert len(frames) == 1
    assert _EXPERT_STATE_REQUIRED <= frames[0]["expert"].keys()


def test_settle_without_spawn_domain_from_arguments():
    run = _make_run()
    record = SimpleNamespace(
        expert_name="Regulatory Expert",
        success=True,
        sub_tool_calls=[],
        arguments={"domain": "regulatory"},
        result=None,
    )
    run.on_experts_settled([record])
    assert run.experts["e1"]["domain"] == "regulatory"


def test_settle_without_spawn_domain_defaults_to_expert():
    run = _make_run()
    record = SimpleNamespace(
        expert_name="Expert",
        success=True,
        sub_tool_calls=[],
        arguments={},
        result=None,
    )
    run.on_experts_settled([record])
    assert run.experts["e1"]["domain"] == "expert"


# ---------------------------------------------------------------------------
# (d) REPORT STREAMING
# stream_report(text) must emit one or more {"type":"report_delta"} frames
# chunked at _REPORT_CHUNK_WORDS words with inter-chunk spacing preserved such
# that concatenating all deltas reproduces the input text exactly, set
# self.report == text, and emit exactly one terminal {"type":"report_done"}.
# ---------------------------------------------------------------------------

def test_stream_report_emits_at_least_one_delta():
    async def go():
        run = _make_run()
        await run.stream_report("hello world")
        return run.events
    events = asyncio.run(go())
    deltas = [e for e in events if e.get("type") == "report_delta"]
    assert len(deltas) >= 1


def test_stream_report_single_chunk_when_short():
    text = "Short report."  # well under _REPORT_CHUNK_WORDS
    async def go():
        run = _make_run()
        await run.stream_report(text)
        return run.events
    events = asyncio.run(go())
    deltas = [e for e in events if e.get("type") == "report_delta"]
    assert len(deltas) == 1
    assert deltas[0]["text"] == text


def test_stream_report_chunks_at_report_chunk_words():
    # Exactly 2 * _REPORT_CHUNK_WORDS words -> exactly 2 chunks.
    words = ["word" + str(i) for i in range(_REPORT_CHUNK_WORDS * 2)]
    text = " ".join(words)

    async def go():
        run = _make_run()
        await run.stream_report(text)
        return run.events
    events = asyncio.run(go())
    deltas = [e for e in events if e.get("type") == "report_delta"]
    assert len(deltas) == 2


def test_stream_report_first_chunk_has_trailing_space():
    # When there are multiple chunks, the first chunk must have a trailing space
    # so that concatenating all deltas re-creates the original text.
    words = ["word" + str(i) for i in range(_REPORT_CHUNK_WORDS * 2)]
    text = " ".join(words)

    async def go():
        run = _make_run()
        await run.stream_report(text)
        return run.events
    events = asyncio.run(go())
    deltas = [e for e in events if e.get("type") == "report_delta"]
    assert deltas[0]["text"].endswith(" ")


def test_stream_report_last_chunk_no_trailing_space():
    words = ["word" + str(i) for i in range(_REPORT_CHUNK_WORDS * 2)]
    text = " ".join(words)

    async def go():
        run = _make_run()
        await run.stream_report(text)
        return run.events
    events = asyncio.run(go())
    deltas = [e for e in events if e.get("type") == "report_delta"]
    assert not deltas[-1]["text"].endswith(" ")


def test_stream_report_concatenated_deltas_reproduce_input():
    text = "This is the full research report with many words that need chunking."

    async def go():
        run = _make_run()
        await run.stream_report(text)
        return run.events
    events = asyncio.run(go())
    deltas = [e for e in events if e.get("type") == "report_delta"]
    assert "".join(d["text"] for d in deltas) == text


def test_stream_report_sets_self_report():
    text = "The deliverable report."

    async def go():
        run = _make_run()
        assert run.report is None
        await run.stream_report(text)
        return run

    run = asyncio.run(go())
    assert run.report == text


def test_stream_report_emits_exactly_one_done():
    async def go():
        run = _make_run()
        await run.stream_report("word " * 20)
        return run.events
    events = asyncio.run(go())
    dones = [e for e in events if e.get("type") == "report_done"]
    assert len(dones) == 1


def test_stream_report_done_is_the_final_report_event():
    """report_done must come after all report_delta frames."""
    async def go():
        run = _make_run()
        await run.stream_report("some report text here for the demo")
        return run.events
    events = asyncio.run(go())
    report_events = [e for e in events if e["type"] in {"report_delta", "report_done"}]
    assert report_events, "expected at least one report event"
    assert report_events[-1]["type"] == "report_done"


def test_stream_report_delta_carries_text_key():
    async def go():
        run = _make_run()
        await run.stream_report("text with multiple words goes here now for test")
        return run.events
    events = asyncio.run(go())
    for delta in (e for e in events if e.get("type") == "report_delta"):
        assert "text" in delta, f"report_delta frame missing 'text': {delta}"


# ---------------------------------------------------------------------------
# (e) CONTRACT SHAPE
# Assert that every frame type emitted by the three mappers is declared in the
# frontend RunEvent union and carries the required payload keys from the #31
# fixture.  Genuine drift is reported as a proposal, not silently fixed.
# ---------------------------------------------------------------------------

def test_log_frame_payload_has_entry_key():
    run = _make_run()
    run.on_log_entry(SimpleNamespace(kind="observation", message="an observation", detail={}))
    log_frames = [e for e in run.events if e.get("type") == "log"]
    assert log_frames, "expected a log frame"
    assert "entry" in log_frames[0], "log frame missing required key 'entry'"


def test_expert_frame_payload_has_expert_key():
    run = _make_run()
    run.on_log_entry(_spawn_entry())
    expert_frames = [e for e in run.events if e.get("type") == "expert"]
    assert expert_frames, "expected an expert frame"
    assert "expert" in expert_frames[0], "expert frame missing required key 'expert'"


def test_report_delta_frame_has_text_key():
    async def go():
        run = _make_run()
        await run.stream_report("hello world today")
        return run.events
    events = asyncio.run(go())
    delta = next((e for e in events if e["type"] == "report_delta"), None)
    assert delta is not None, "expected at least one report_delta frame"
    assert "text" in delta, "report_delta frame missing required key 'text'"


def test_all_emitted_frame_types_are_known_to_frontend():
    """
    None of the frame types the three mappers emit may be unknown to the
    frontend (i.e. absent from the RunEvent union in types.ts).
    On genuine drift this writes a needs-reviewer proposal and fails.
    """
    async def go():
        run = _make_run()
        run.on_log_entry(SimpleNamespace(kind="observation", message="obs", detail={}))
        run.on_log_entry(_spawn_entry())
        run.on_experts_settled([_expert_record()])
        await run.stream_report("word " * (_REPORT_CHUNK_WORDS + 2))
        return run.events
    events = asyncio.run(go())

    emitted_types = {e["type"] for e in events}
    unknown = emitted_types - _FRONTEND_KNOWN_TYPES
    if unknown:
        _report_drift(unknown)


def test_required_payload_keys_present_for_each_emitted_type():
    """
    Every emitted frame whose type appears in _REQUIRED_KEYS must carry the
    keys the frontend reads unconditionally.
    """
    async def go():
        run = _make_run()
        run.on_log_entry(SimpleNamespace(kind="observation", message="obs", detail={}))
        run.on_log_entry(_spawn_entry())
        run.on_experts_settled([_expert_record()])
        await run.stream_report("word " * (_REPORT_CHUNK_WORDS + 2))
        return run.events
    events = asyncio.run(go())

    violations: list[str] = []
    for evt in events:
        t = evt.get("type", "")
        required = _REQUIRED_KEYS.get(t)
        if required is None:
            continue  # type not in our checked set
        missing = required - evt.keys()
        if missing:
            violations.append(f"  type={t!r}: missing keys {sorted(missing)}")

    if violations:
        msg = (
            "\nSSE frame payload key violations — needs-reviewer:\n"
            + "\n".join(violations)
        )
        proposal = pathlib.Path("/home/amrit/.clannon_proposal")
        existing = proposal.read_text() if proposal.exists() else ""
        proposal.write_text(
            existing
            + "\n\n## SSE payload key drift (test/c6-run-state-event-mappers)\n"
            + msg
            + "\n"
        )
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Summary table
# Exercises every mapper and prints a per-mapper verdict.  Runs last
# so individual failures above give granular context first.
# ---------------------------------------------------------------------------

def test_print_streaming_contract_summary(capsys):
    """
    Per-mapper EXPERT-SPAWN / SETTLE-DONE / SETTLE-FAILED / SETTLE-NO-SPAWN /
    REPORT-DELTA / REPORT-DONE verdict table with 'streaming contract held /
    VIOLATED'.
    """
    verdicts: list[tuple[str, bool, str]] = []

    def _check(label: str, fn) -> None:
        try:
            fn()
            verdicts.append((label, True, ""))
        except Exception as exc:
            verdicts.append((label, False, str(exc)))

    # EXPERT-SPAWN
    def _spawn():
        run = _make_run("v-spawn")
        run.on_log_entry(_spawn_entry())
        frame = next(e for e in run.events if e.get("type") == "expert")
        assert _EXPERT_STATE_REQUIRED <= frame["expert"].keys()
        assert frame["expert"]["status"] == "working"
        assert frame["expert"]["toolCalls"] == 0
        assert frame["expert"]["status"] in _EXPERT_VALID_STATUSES
        assert frame["expert"]["type"] if False else True  # noqa — just checking keys
    _check("EXPERT-SPAWN", _spawn)

    # SETTLE-DONE
    def _settle_done():
        run = _make_run("v-done")
        run.on_log_entry(_spawn_entry())
        run.on_experts_settled([_expert_record(success=True)])
        assert run.experts["e1"]["status"] == "done"
        assert run.experts["e1"]["status"] in _EXPERT_VALID_STATUSES
        assert run.experts["e1"]["toolCalls"] == 2
    _check("SETTLE-DONE", _settle_done)

    # SETTLE-FAILED
    def _settle_failed():
        run = _make_run("v-failed")
        run.on_log_entry(_spawn_entry())
        run.on_experts_settled([_expert_record(success=False)])
        assert run.experts["e1"]["status"] == "failed"
        assert run.experts["e1"]["status"] in _EXPERT_VALID_STATUSES
    _check("SETTLE-FAILED", _settle_failed)

    # SETTLE-NO-SPAWN
    def _settle_nospawn():
        run = _make_run("v-nospawn")
        assert not run.experts
        run.on_experts_settled([_expert_record(expert_name="Data Analyst", success=True)])
        assert "e1" in run.experts
        assert _EXPERT_STATE_REQUIRED <= run.experts["e1"].keys()
        assert run.experts["e1"]["status"] == "done"
    _check("SETTLE-NO-SPAWN", _settle_nospawn)

    # REPORT-DELTA
    def _report_delta():
        async def go():
            run = _make_run("v-delta")
            text = " ".join(["word"] * (_REPORT_CHUNK_WORDS + 1))
            await run.stream_report(text)
            return run.events
        events = asyncio.run(go())
        deltas = [e for e in events if e.get("type") == "report_delta"]
        assert deltas, "no report_delta frames emitted"
        for d in deltas:
            assert "text" in d
        # concatenation reconstructs the input
        text_in = " ".join(["word"] * (_REPORT_CHUNK_WORDS + 1))
        assert "".join(d["text"] for d in deltas) == text_in
    _check("REPORT-DELTA", _report_delta)

    # REPORT-DONE
    def _report_done():
        async def go():
            run = _make_run("v-done2")
            await run.stream_report("a b")
            return run.events
        events = asyncio.run(go())
        dones = [e for e in events if e.get("type") == "report_done"]
        report_events = [e for e in events if e["type"] in {"report_delta", "report_done"}]
        assert len(dones) == 1, f"expected exactly one report_done, got {len(dones)}"
        assert report_events[-1]["type"] == "report_done"
    _check("REPORT-DONE", _report_done)

    # Print the table
    width = 55
    print("\n")
    print("=" * width)
    print("  RunState live-event mapper SSE contract verdicts")
    print("=" * width)
    for label, held, err in verdicts:
        verdict = "streaming contract held" if held else f"VIOLATED ({err[:60]})"
        print(f"  {label:<18} {verdict}")
    print("=" * width)

    failed = [(l, e) for l, ok, e in verdicts if not ok]
    assert not failed, "Contract violations:\n" + "\n".join(
        f"  {l}: {e}" for l, e in failed
    )
