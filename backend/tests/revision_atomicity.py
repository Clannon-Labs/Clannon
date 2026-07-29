"""Atomic soft-supersession failure and provenance guarantees."""

from types import SimpleNamespace

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from api import config, run_store

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "atomic-revision.db"))
    return run_store.RunStore()


class _Task:
    cancelled = False

    def cancel(self):
        self.cancelled = True


def test_registration_write_failure_leaves_original_chat_unchanged(
    store, monkeypatch
):
    from api import run_store

    target = store.create("u1", "original")
    target.status = "delivered"
    task = _Task()

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(run_store, "write_run", fail_write)
    with pytest.raises(RuntimeError, match="write failed"):
        store.create_revision("u1", "edited", target, start=lambda _run: task)

    assert task.cancelled is True
    assert store.get("u1", target.id) is target
    assert [run.id for run in store.list_for("u1")] == [target.id]


def test_supersession_retains_usage_memory_and_audit_provenance(store):
    from api import audit, decision_audit

    target = store.create("u1", "original")
    target.status = "delivered"
    target.tokens_used = 321
    target.memory_writes = [
        {"content": "saved", "ts": "2026-07-29T00:00:00+00:00"}
    ]
    store.persist(target)
    audit.write_block_record(
        user_id="u1", session_id=target.session_id, trace_id=target.id,
        block_code="blocked", threat_level="high", origin="verifier", reason="reason",
    )
    decision_audit.write_decision_records(
        user_id="u1", session_id=target.session_id, trace_id=target.id,
        records=[SimpleNamespace(
            turn=1, kind="answer", decision="decision", reasoning="why",
            participants=[], ts=1.0,
        )],
    )

    revised = store.create_revision("u1", "edited", target)
    internal = store.list_for("u1", include_superseded=True)

    assert store.get("u1", target.id) is None
    assert {run.id for run in internal} == {target.id, revised.id}
    old = next(run for run in internal if run.id == target.id)
    assert old.tokens_used == 321
    assert old.memory_writes[0]["content"] == "saved"
    assert len(audit.get_for_run("u1", target.id)) == 1
    assert len(decision_audit.get_for_run("u1", target.id)) == 1
    assert "superseded" not in revised.full_json()
