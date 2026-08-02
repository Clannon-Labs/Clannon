"""Run-timing telemetry: `started_at` / `first_message_at` / `completed_at`, and
the `/usage` latency aggregate built from them.

Two layers:

1. `RunState`/`run_driver` mechanics — proves the ONE thing the brief calling for
   this work warned against: `first_message_at` must be stamped ONLY at the live
   narration site (`run_state.py`'s `on_log_entry`, `kind == "message"`), never
   from `report_delta` chunking (`stream_report`) or the report-mode direct
   `message_delta` shortcut (`run_driver.execute`'s `_final_msg` path). Both of
   those fire terminal-adjacent, a few hundred ms before the run finishes, and a
   "time to first value" built from either would really be time-to-nearly-done.
   Driven through `run_driver.execute()` with a faked `pipeline.run` — same
   hermetic pattern as `tests/completion_state.py`.

2. `billing.usage_summary`'s `latency` aggregate — TWO independent samples,
   each requiring only its own pair of stamps: `totalDurationMs` needs
   `started_at`+`completed_at`; `timeToFirstMessageMs` needs `started_at`+
   `first_message_at`. A report-mode run with no live narration can be
   `delivered` with real content and still miss `first_message_at` — that must
   not disqualify its (perfectly good) `totalDurationMs` measurement. Each
   sample carries its own `sampleSize`/`excluded`; an empty sample reports
   `null`, never `0`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import api.run_driver as rd
from api.run_state import RunState


# ---------------------------------------------------------------------------
# A deterministic clock so ordering assertions are exact, not timing-flaky.
# `_now` is imported by value into `run_driver` at module-load time, so both
# call sites need patching to stay on the same sequence.
# ---------------------------------------------------------------------------


def _install_fake_clock(monkeypatch):
    counter = {"n": 0}

    def _clock() -> str:
        counter["n"] += 1
        return f"2026-01-01T00:00:{counter['n']:02d}+00:00"

    monkeypatch.setattr("api.run_state._now", _clock)
    monkeypatch.setattr(rd, "_now", _clock)
    return _clock


def _fake_flow(*, presentation="report", message="", final_response="the draft answer"):
    ctx = SimpleNamespace(
        blocked=False,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=False,
        filter_result=SimpleNamespace(groundedness="grounded"),
        failed=False,
        failure_error=None,
        orchestrator_response=SimpleNamespace(
            text=final_response, message=message,
            metadata={}, presentation=presentation,
        ),
        final_response=final_response,
        memory_writes_requested=[],
        memory_writes_persisted=[],
        expert_findings=[],
        expert_calls=[],
        tool_calls=[],
    )
    return SimpleNamespace(ctx=ctx)


def _drive(monkeypatch, flow, *, narrate: list[str] | None = None) -> RunState:
    """Run `rd.execute()` against a faked pipeline that optionally narrates live
    (appends `kind="message"` entries to the observing `decision_log` sink,
    exactly as the real orchestrator's `say()` tool does mid-run)."""
    async def fake_run(*a, decision_log=None, **k):
        for text in narrate or []:
            decision_log.append(SimpleNamespace(kind="message", message=text, detail={}))
        return flow

    monkeypatch.setattr(rd.pipeline, "run", fake_run)
    monkeypatch.setattr(rd, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(rd.STORE, "session_turns", lambda *a, **k: [])
    monkeypatch.setattr(rd.STORE, "persist", lambda run: None)

    run = RunState(id="r1", user_id="u", title="t", brief="b", session_id="r1")
    asyncio.run(rd.execute(run))
    return run


# ---------------------------------------------------------------------------
# 1. RunState / run_driver stamping mechanics
# ---------------------------------------------------------------------------


def test_started_at_stamped_before_the_stage_chain(monkeypatch):
    _install_fake_clock(monkeypatch)
    run = _drive(monkeypatch, _fake_flow())
    assert run.started_at is not None


def test_completed_at_stamped_only_at_the_terminal_choke_point(monkeypatch):
    _install_fake_clock(monkeypatch)
    run = _drive(monkeypatch, _fake_flow())
    assert run.completed_at is not None
    # completed_at must come after started_at on the fake clock's sequence
    assert run.completed_at > run.started_at


def test_live_narration_stamps_first_message_at_once(monkeypatch):
    """Two `say()` calls during the run must not move the stamp off the first."""
    _install_fake_clock(monkeypatch)
    run = _drive(
        monkeypatch, _fake_flow(),
        narrate=["let me look into that", "still working on it"],
    )
    assert run.first_message_at is not None
    # separates from completed_at, materially (the fake clock ticks once per
    # call — the second narration and the terminal stamp both land LATER)
    assert run.first_message_at < run.completed_at


def test_report_mode_without_live_narration_leaves_first_message_at_unset(monkeypatch):
    """The one thing the brief said never to do: a report-mode run with no live
    `say()` delivers real content (a conversational note + the report) entirely
    through `stream_report`'s `report_delta` chunking and the report-mode direct
    `message_delta` shortcut (`run_driver.execute` lines ~265-268) — NEITHER of
    which is the stamping site. `first_message_at` must stay None even though
    the run genuinely delivered."""
    _install_fake_clock(monkeypatch)
    run = _drive(
        monkeypatch,
        _fake_flow(presentation="report", message="here is a short note"),
    )
    assert run.status == "delivered"
    assert run.message == "here is a short note"
    assert run.report is not None
    assert run.first_message_at is None
    # a run with no timing pair still gets started_at/completed_at — it is the
    # *pair* that is missing, which is exactly what excludes it downstream
    assert run.started_at is not None
    assert run.completed_at is not None


def test_chat_mode_final_answer_without_live_narration_does_stamp(monkeypatch):
    """Chat-mode's only content IS the final answer, delivered through
    `on_log_entry` (run_driver.execute ~375-381) — the real stamping site — so
    it legitimately counts as first content, unlike the report-mode shortcut."""
    _install_fake_clock(monkeypatch)
    run = _drive(
        monkeypatch,
        _fake_flow(presentation="chat", final_response="the direct chat answer"),
    )
    assert run.status == "delivered"
    assert run.first_message_at is not None


def test_blocked_run_never_gets_first_message_at(monkeypatch):
    _install_fake_clock(monkeypatch)
    flow = _fake_flow()
    flow.ctx.blocked = True
    flow.ctx.sanitization_blocked = True
    run = _drive(monkeypatch, flow)
    assert run.status == "blocked"
    assert run.first_message_at is None
    # still terminal — completed_at is honest regardless of outcome
    assert run.completed_at is not None


def test_emit_and_stream_report_never_stamp_first_message_at():
    """Direct unit check on the mechanism itself, independent of run_driver:
    generic `emit()` and `stream_report()`'s `report_delta`/`report_done` must
    never touch `first_message_at` — only `on_log_entry`'s `kind == "message"`
    branch may."""
    run = RunState(id="r1", user_id="u", title="t", brief="b")
    run.emit({"type": "status", "status": "queued"})
    run.emit({"type": "sources", "sources": []})
    assert run.first_message_at is None

    asyncio.run(run.stream_report("a short report body"))
    assert run.first_message_at is None
    assert run.report == "a short report body"


def test_on_log_entry_message_stamps_exactly_once():
    run = RunState(id="r1", user_id="u", title="t", brief="b")
    run.on_log_entry(SimpleNamespace(kind="message", message="first", detail={}))
    first_stamp = run.first_message_at
    assert first_stamp is not None

    run.on_log_entry(SimpleNamespace(kind="message", message="second", detail={}))
    assert run.first_message_at == first_stamp


def test_timing_fields_are_in_summary_json():
    run = RunState(id="r1", user_id="u", title="t", brief="b")
    assert run.summary_json()["startedAt"] is None
    assert run.summary_json()["firstMessageAt"] is None
    assert run.summary_json()["completedAt"] is None

    run.started_at = "2026-01-01T00:00:01+00:00"
    run.first_message_at = "2026-01-01T00:00:02+00:00"
    run.completed_at = "2026-01-01T00:00:03+00:00"
    js = run.summary_json()
    assert js["startedAt"] == run.started_at
    assert js["firstMessageAt"] == run.first_message_at
    assert js["completedAt"] == run.completed_at


# ---------------------------------------------------------------------------
# 2. billing.usage_summary's latency aggregate
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_env(tmp_path, monkeypatch):
    from api import auth, config, run_store
    import api.runs as runs_mod
    import api.billing as billing_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "timing.db"))
    monkeypatch.setattr(config, "DEFAULT_PLAN", "free")
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)

    with auth._db() as db:
        db.execute(
            "INSERT INTO users (id, email, name, pw_hash, pw_salt, plan, created_at) "
            "VALUES ('u1','u1@example.com','U','x','y','free', ?)",
            (1700000000.0,),
        )
    return SimpleNamespace(store=store, billing=billing_mod)


def _timed_run(store, *, rid, status, started=None, first=None, completed=None):
    run = store.create("u1", "some work")
    run.id = rid
    run.status = status
    run.started_at = started
    run.first_message_at = first
    run.completed_at = completed
    store.persist(run)
    return run


def test_full_triple_enters_both_samples(store_env):
    _timed_run(
        store_env.store, rid="run_a", status="delivered",
        started="2026-01-01T00:00:00+00:00",
        first="2026-01-01T00:00:01+00:00",
        completed="2026-01-01T00:00:05+00:00",
    )
    # blocked: started + completed present, no live output — excluded from
    # timeToFirstMessageMs only, still counts toward totalDurationMs
    _timed_run(
        store_env.store, rid="run_b", status="blocked",
        started="2026-01-01T00:00:00+00:00",
        first=None,
        completed="2026-01-01T00:00:02+00:00",
    )
    # failed before the stage chain ever started — no stamps at all
    _timed_run(store_env.store, rid="run_c", status="failed")

    usage = store_env.billing.usage_summary("u1")
    latency = usage["latency"]
    assert latency["inPeriod"] == 3
    assert latency["timeToFirstMessageMs"]["sampleSize"] == 1
    assert latency["timeToFirstMessageMs"]["excluded"] == 2
    assert latency["timeToFirstMessageMs"]["p50"] == 1000
    assert latency["totalDurationMs"]["sampleSize"] == 2
    assert latency["totalDurationMs"]["excluded"] == 1
    assert latency["totalDurationMs"]["p50"] == 3500


def test_report_mode_run_without_narration_counts_duration_not_first_message(store_env):
    """The discriminating case: started_at + completed_at present, first_message_at
    absent (a report-mode delivery with no live `say()`). Must appear in
    totalDurationMs and must NOT appear in timeToFirstMessageMs — this is exactly
    the case the all-three rule silently discarded."""
    _timed_run(
        store_env.store, rid="run_report", status="delivered",
        started="2026-01-01T00:00:00+00:00",
        first=None,
        completed="2026-01-01T00:04:00+00:00",
    )
    latency = store_env.billing.usage_summary("u1")["latency"]
    assert latency["timeToFirstMessageMs"]["sampleSize"] == 0
    assert latency["timeToFirstMessageMs"]["excluded"] == 1
    assert latency["totalDurationMs"]["sampleSize"] == 1
    assert latency["totalDurationMs"]["excluded"] == 0
    assert latency["totalDurationMs"]["p50"] == 240000


def test_excluded_runs_never_move_the_percentiles(store_env):
    _timed_run(
        store_env.store, rid="run_a", status="delivered",
        started="2026-01-01T00:00:00+00:00",
        first="2026-01-01T00:00:01+00:00",
        completed="2026-01-01T00:00:05+00:00",
    )
    before = store_env.billing.usage_summary("u1")["latency"]

    # missing started_at entirely — excluded from both samples
    _timed_run(
        store_env.store, rid="run_d", status="cancelled",
        started=None,
        first=None, completed="2026-01-01T00:01:00+00:00",
    )
    after = store_env.billing.usage_summary("u1")["latency"]

    assert after["timeToFirstMessageMs"]["sampleSize"] == before["timeToFirstMessageMs"]["sampleSize"] == 1
    assert after["totalDurationMs"]["sampleSize"] == before["totalDurationMs"]["sampleSize"] == 1
    assert after["timeToFirstMessageMs"]["p50"] == before["timeToFirstMessageMs"]["p50"]
    assert after["totalDurationMs"]["p50"] == before["totalDurationMs"]["p50"]
    assert after["timeToFirstMessageMs"]["excluded"] == before["timeToFirstMessageMs"]["excluded"] + 1
    assert after["totalDurationMs"]["excluded"] == before["totalDurationMs"]["excluded"] + 1


def test_empty_sample_reports_null_not_zero(store_env):
    usage = store_env.billing.usage_summary("u1")
    latency = usage["latency"]
    assert latency["inPeriod"] == 0
    assert latency["timeToFirstMessageMs"]["sampleSize"] == 0
    assert latency["timeToFirstMessageMs"]["excluded"] == 0
    assert latency["timeToFirstMessageMs"]["p50"] is None
    assert latency["timeToFirstMessageMs"]["p95"] is None
    assert latency["totalDurationMs"]["sampleSize"] == 0
    assert latency["totalDurationMs"]["excluded"] == 0
    assert latency["totalDurationMs"]["p50"] is None
    assert latency["totalDurationMs"]["p95"] is None


def test_pre_migration_row_reads_null_and_is_excluded(store_env, monkeypatch):
    """A row written before this migration has no timing columns at all. It must
    read back NULL (never 0 — a 0 duration would drag every percentile down
    dishonestly) and must not blow up `usage_summary`."""
    from api import auth

    with auth._db() as db:
        db.execute(
            "INSERT INTO runs (id,user_id,title,brief,status,created_at) "
            "VALUES ('run_old','u1','old','old brief','delivered',?)",
            (datetime.now(timezone.utc).isoformat(),),
        )

    restored = store_env.store.get("u1", "run_old")
    assert restored.started_at is None
    assert restored.first_message_at is None
    assert restored.completed_at is None

    usage = store_env.billing.usage_summary("u1")
    assert usage["latency"]["timeToFirstMessageMs"]["sampleSize"] == 0
    assert usage["latency"]["timeToFirstMessageMs"]["excluded"] == 1
    assert usage["latency"]["totalDurationMs"]["sampleSize"] == 0
    assert usage["latency"]["totalDurationMs"]["excluded"] == 1
