"""
Session continuity: the whole session is replayed as chat history (with the message
channel + attachment notes, trimmed only when huge), and files uploaded in an earlier
turn are persisted and re-loaded so a later turn can still read them.
"""

import asyncio
from types import SimpleNamespace

from foundation import InputFile
import api.run_driver as rd


def _turn(tid, brief, *, message=None, report=None, status="delivered", inputs=None, ts="2026-06-18T00:00:01"):
    return SimpleNamespace(
        id=tid, brief=brief, message=message, report=report, status=status,
        inputs=inputs or [], created_at=ts, experts={}, log=[],
    )


def test_history_includes_message_channel_and_attachments(monkeypatch):
    turns = [
        _turn("r1", "look at this", message="Sure — what angle?", inputs=[{"name": "data.csv"}], ts="2026-06-18T00:00:01"),
        _turn("r2", "the market", message="Here it is.", report="# Brief", ts="2026-06-18T00:00:02"),
    ]
    monkeypatch.setattr(rd.STORE, "session_turns", lambda u, s: turns)
    run = SimpleNamespace(id="r3", user_id="u", session_id="r1", created_at="2026-06-18T00:00:03")
    convo = rd._build_conversation(run)

    assert "[attached file(s) this turn: data.csv]" in convo[0]["content"]
    assert convo[1]["content"] == "Sure — what angle?"          # a message-only turn is kept (not "no answer")
    assert "Here it is." in convo[3]["content"] and "# Brief" in convo[3]["content"]
    assert len(convo) == 4                                       # both turns kept whole


def test_history_trims_oldest_when_over_budget(monkeypatch):
    big = "x" * 80_000
    turns = [_turn(f"r{i}", "q", report=big, ts=f"2026-06-18T00:00:0{i}") for i in range(1, 5)]  # ~320k chars
    monkeypatch.setattr(rd.STORE, "session_turns", lambda u, s: turns)
    run = SimpleNamespace(id="r9", user_id="u", session_id="r1", created_at="2026-06-18T00:00:09")
    convo = rd._build_conversation(run)
    kept_turns = len(convo) // 2
    assert 1 <= kept_turns < 4                                   # oldest dropped to fit the budget
    # the MOST RECENT turn is always kept
    assert convo[-2]["content"] == "q"


def test_uploaded_file_survives_to_a_later_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("VRAKSHA_ARTIFACTS_DIR", str(tmp_path))

    async def go():
        run1 = SimpleNamespace(id="rf1", user_id="u", session_id="rf1", inputs=None, created_at="2026-06-18T00:00:01")
        f = InputFile(name="data.csv", modality="text", data=b"a,b,c\n1,2,3", size=10)
        await rd.persist_inputs(run1, [f])
        assert run1.inputs and run1.inputs[0].get("id")          # ref recorded on the turn

        monkeypatch.setattr(rd.STORE, "session_turns", lambda u, s: [run1])
        run2 = SimpleNamespace(id="rf2", user_id="u", session_id="rf1", created_at="2026-06-18T00:00:02")
        gathered = await rd._gather_session_files(run2, [])      # follow-up uploads nothing

        assert [g.name for g in gathered] == ["data.csv"]        # the earlier file is present
        assert gathered[0].data == b"a,b,c\n1,2,3"               # bytes re-loaded from the store

    asyncio.run(go())


def test_deleting_a_session_purges_its_stored_files(monkeypatch, tmp_path):
    monkeypatch.setenv("VRAKSHA_ARTIFACTS_DIR", str(tmp_path))
    from api.run_store import _purge_run_files, INPUT_NS
    from core.artifacts import LocalArtifactStore

    async def setup():
        store = LocalArtifactStore()
        await store.put("rdx", "out.md", b"a delivered artifact")     # output artifact
        await store.put(f"{INPUT_NS}rdx", "in.csv", b"an uploaded file")  # uploaded input

    asyncio.run(setup())
    assert (tmp_path / "rdx").is_dir() and (tmp_path / f"{INPUT_NS}rdx").is_dir()

    _purge_run_files({"rdx"})   # what delete_session calls after removing the rows

    assert not (tmp_path / "rdx").exists()              # output artifacts gone
    assert not (tmp_path / f"{INPUT_NS}rdx").exists()   # uploaded inputs gone
