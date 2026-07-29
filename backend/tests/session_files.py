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


def test_history_condenses_oldest_when_over_budget(monkeypatch):
    # 4 big turns over the budget: the oldest are CONDENSED into a recap, NEVER dropped (W8)
    big = "x" * 80_000
    turns = [_turn(f"r{i}", f"question number {i}", report=big, ts=f"2026-06-18T00:00:0{i}") for i in range(1, 5)]
    monkeypatch.setattr(rd.STORE, "session_turns", lambda u, s: turns)
    run = SimpleNamespace(id="r9", user_id="u", session_id="r1", created_at="2026-06-18T00:00:09")
    convo = rd._build_conversation(run)

    # the most recent turn is always kept verbatim
    assert convo[-2]["content"] == "question number 4"
    # the oldest turns are not gone — they're summarized into a recap folded onto the first message
    assert "CONVERSATION RECAP" in convo[0]["content"]
    assert "question number 1" in convo[0]["content"]           # turn 1 still represented, not deleted
    assert "recall" in convo[0]["content"].lower()              # and the model is told it can pull it back


def test_full_transcript_keeps_every_turn_for_recall(monkeypatch):
    # the untrimmed transcript (for the recall tool) keeps EVERY prior turn, condensed or not
    turns = [_turn(f"r{i}", f"question {i}", report=f"answer {i}", ts=f"2026-06-18T00:00:0{i}") for i in range(1, 5)]
    monkeypatch.setattr(rd.STORE, "session_turns", lambda u, s: turns)
    run = SimpleNamespace(id="r9", user_id="u", session_id="r1", created_at="2026-06-18T00:00:09")
    transcript = rd._build_transcript(run)

    assert [t["n"] for t in transcript] == [1, 2, 3, 4]         # every prior turn, none dropped
    assert transcript[0]["user"] == "question 1" and "answer 1" in transcript[0]["assistant"]


def test_uploaded_file_survives_to_a_later_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("VRAKSHA_ARTIFACTS_DIR", str(tmp_path))

    async def go():
        run1 = SimpleNamespace(id="rf1", user_id="u", session_id="rf1", inputs=None, created_at="2026-06-18T00:00:01")
        data = b"a,b,c\n1,2,3"
        f = InputFile(name="data.csv", modality="text", data=data, size=len(data))
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
