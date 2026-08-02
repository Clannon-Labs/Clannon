"""
Persistence round-trip contract for `RunState`.

`RunStore.persist()` writes a finished run to SQLite and `_from_row()` reads it
back. The two must stay in lock-step: every field that is meant to survive a
server restart has to be on BOTH sides, or history silently loses data. These
tests pin that contract WITHOUT touching `RunState` — they build a run with every
persistable field set to a distinctive non-default value, round-trip it through a
throwaway DB, and assert nothing was dropped (object fields AND the `full_json`
REST shape the frontend consumes).

The field-set snapshot test is the real guard: adding a field to `RunState` fails
it until the author classifies the field as persisted (and wires both sides) or
runtime-only, so a new field can't quietly skip persistence.
"""

from dataclasses import fields

import pytest

from api.run_state import RunState


# The fields deliberately NOT written through to SQLite: pure runtime state (live
# queues, the cancel task handle, in-flight flags) and `session_models`, which is
# consumed at execute time and gone by the time a terminal run is persisted.
RUNTIME_ONLY = {
    "events",
    "subscribers",
    "task",
    "cancel_requested",
    "deleted",
    "session_models",
}

# The fields that MUST survive persist() -> _from_row(). Kept explicit (rather than
# derived) so this list is the human-readable persistence contract.
PERSISTED = {
    "id",
    "user_id",
    "title",
    "brief",
    "status",
    "created_at",
    "log",
    "experts",
    "report",
    "message",
    "tokens_used",
    "cache_read_tokens",
    "cache_write_tokens",
    "artifacts",
    "inputs",
    "memory_writes",
    "feedback_rating",
    "feedback_comment",
    "parent_run_id",
    "block_stage",
    "session_id",
    "project_id",
    "sources",
    "verification_state",
    "completion_state",
    "completion_reason",
    "lineage_prefix",
    "superseded",
    "started_at",
    "first_message_at",
    "completed_at",
}

# Required positional fields (no default) — always set by any caller, so they can
# never be "missed"; excluded from the non-default sanity check below.
_REQUIRED = {"id", "user_id", "title", "brief"}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A RunStore backed by a throwaway SQLite file — no shared state, no pipeline."""
    from api import config, run_store

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "roundtrip.db"))
    return run_store.RunStore()


def _fully_populated_run() -> RunState:
    """A run with EVERY persistable field at a distinctive non-default value.

    Not a realistic run (a delivered run wouldn't normally carry a block_stage):
    the point is to max out the serializer so any dropped field shows up as a
    mismatch after the round-trip.
    """
    run = RunState(
        id="run_roundtrip01",
        user_id="u_owner",
        title="Round-trip contract run",
        brief="the original brief that must come back verbatim",
        status="delivered",
        created_at="2026-06-20T12:34:56+00:00",
    )
    run.tokens_used = 4242
    run.cache_read_tokens = 9001
    run.cache_write_tokens = 777
    run.log = [
        {"id": "log_aa", "ts": "2026-06-20T12:35:00+00:00", "kind": "tool_call",
         "title": "web_search", "meta": {"query": "clannon"}},
        {"id": "log_bb", "ts": "2026-06-20T12:35:01+00:00", "kind": "expert_spawn",
         "title": "spawned researcher"},
    ]
    run.experts = {
        "e1": {"id": "e1", "name": "Researcher", "domain": "web",
               "status": "done", "toolCalls": 3, "summary": "found the answer"},
        "e2": {"id": "e2", "name": "Analyst", "domain": "data",
               "status": "failed", "toolCalls": 0},
    }
    run.report = "# Report\n\nThe full deliverable body."
    run.message = "Here is the conversational reply for the chat bubble."
    run.artifacts = [{"name": "report.pdf", "kind": "output", "size": 2048,
                      "id": "art_1", "ref": "run_roundtrip01/report.pdf"}]
    run.inputs = [{"name": "brief.docx", "modality": "document", "size": 4096}]
    run.memory_writes = [{"id": "run_roundtrip01_m0", "content": "a remembered fact",
                          "store": "semantic"}]
    run.feedback_rating = "up"
    run.feedback_comment = "great work, thanks"
    run.parent_run_id = "run_parent99"
    run.block_stage = "filter"
    run.session_id = "run_session01"
    run.project_id = "proj_xyz"
    run.sources = [{"id": "src_1", "title": "example.com — clannon",
                    "url": "https://example.com/clannon", "domain": "example.com"}]
    run.verification_state = "grounded"
    # distinctive non-default: the default is "complete"/None, so a dropped column
    # would still look right if we round-tripped the default.
    run.completion_state = "partial"
    run.completion_reason = "timeout"
    run.lineage_prefix = ["run_prefix01", "run_prefix02"]
    run.superseded = True
    run.started_at = "2026-06-20T12:34:57+00:00"
    run.first_message_at = "2026-06-20T12:34:58+00:00"
    run.completed_at = "2026-06-20T12:35:10+00:00"
    return run


def test_persisted_field_set_matches_runstate(store):
    """If a field is added to RunState, force a decision: persisted or runtime-only.

    This is the guard that keeps persist()/_from_row() honest as RunState grows —
    a new field that lands in neither bucket trips this assertion immediately.
    """
    declared = {f.name for f in fields(RunState)}
    classified = PERSISTED | RUNTIME_ONLY
    assert declared == classified, (
        "RunState fields changed — classify each as PERSISTED (and wire persist() "
        f"+ _from_row()) or RUNTIME_ONLY. Unclassified: {declared - classified}; "
        f"stale: {classified - declared}"
    )
    assert not (PERSISTED & RUNTIME_ONLY)   # a field can't be both


def test_test_data_exercises_every_persisted_field():
    """The round-trip can only catch a dropped field if the field carried a
    non-default value to begin with. Verify the fixture populates each one."""
    run = _fully_populated_run()
    defaults = RunState(id=run.id, user_id=run.user_id, title=run.title, brief=run.brief)
    for name in PERSISTED - _REQUIRED:
        assert getattr(run, name) != getattr(defaults, name), (
            f"_fully_populated_run() left {name!r} at its default — pick a "
            "distinctive value so the round-trip actually tests it"
        )


def test_runstate_survives_persist_and_from_row(store):
    """Every persisted field comes back byte-for-byte after persist() -> get()."""
    original = _fully_populated_run()
    store.persist(original)

    restored = store.list_for(original.user_id, include_superseded=True)[0]
    assert restored is not None, "persisted run did not come back from get()"

    for name in PERSISTED:
        assert getattr(restored, name) == getattr(original, name), (
            f"field {name!r} did not survive the persist/_from_row round-trip"
        )


def test_full_json_is_stable_across_a_round_trip(store):
    """The REST contract the frontend reads (`full_json`) is identical before and
    after persistence — no field exposed to the UI is lost on a restart."""
    original = _fully_populated_run()
    before = original.full_json()

    store.persist(original)
    restored = store.list_for(original.user_id, include_superseded=True)[0]

    assert restored.full_json() == before


def test_get_is_owner_scoped_after_persist(store):
    """A persisted run is only readable by its owner — the round-trip must not
    widen access (the row's user_id is the auth boundary)."""
    original = _fully_populated_run()
    store.persist(original)

    assert store.list_for("someone_else", include_superseded=True) == []
    assert store.get(original.user_id, original.id) is None
    assert store.list_for(original.user_id, include_superseded=True)[0].id == original.id


def test_existing_database_migrates_additive_run_columns(tmp_path, monkeypatch):
    """Old SQLite files gain new run metadata without hiding existing runs."""
    import sqlite3

    from api import auth, config
    from api.run_store import RunStore

    db_path = tmp_path / "pre_branch.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """CREATE TABLE runs (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
                brief TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                log_json TEXT NOT NULL DEFAULT '[]',
                experts_json TEXT NOT NULL DEFAULT '[]',
                report TEXT, memory_writes_json TEXT NOT NULL DEFAULT '[]'
            )"""
        )
        db.execute(
            "INSERT INTO runs (id,user_id,title,brief,status,created_at) "
            "VALUES ('run_old','u1','old','old brief','delivered','2026-01-01')"
        )

    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    with auth._db() as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
        row = db.execute(
            "SELECT lineage_prefix_json, superseded, cache_read_tokens, "
            "cache_write_tokens FROM runs WHERE id='run_old'"
        ).fetchone()

    assert "lineage_prefix_json" in columns
    assert row["lineage_prefix_json"] is None
    assert "superseded" in columns
    assert row["superseded"] == 0
    assert "cache_read_tokens" in columns
    assert "cache_write_tokens" in columns
    assert row["cache_read_tokens"] == 0
    assert row["cache_write_tokens"] == 0

    restored = RunStore().get("u1", "run_old")
    assert restored is not None
    assert restored.full_json()["cacheReadTokens"] == 0
    assert restored.full_json()["cacheWriteTokens"] == 0
