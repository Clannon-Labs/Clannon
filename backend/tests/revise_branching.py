"""Safe in-place turn revision across HTTP, history, files, and persistence."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from foundation import Flow, InputFile


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Fresh owner-scoped API store with execution captured before scheduling."""
    from api import config, run_driver, run_store
    import api.runs as runs_mod
    import api.run_revision as revision_mod
    from core.memory import manager

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "revise.db"))
    # Project-scoped wiki hydration is a starter-tier behavior.
    monkeypatch.setattr(config, "DEFAULT_PLAN", "starter")
    monkeypatch.setenv("VRAKSHA_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)
    monkeypatch.setattr(run_driver, "STORE", store)
    monkeypatch.setattr(revision_mod.runs, "STORE", store)
    async def empty_memory(_user_id):
        return []
    monkeypatch.setattr(manager, "list_entries", empty_memory)

    executions = []

    def capture_execute(run, input_files=None):
        executions.append((run, list(input_files or [])))

        async def complete():
            return None

        return complete()

    monkeypatch.setattr(runs_mod, "execute", capture_execute)

    app_mod = importlib.import_module("api.app")
    app_mod._auth_attempts.clear()
    client = TestClient(app_mod.app)
    owner = _signup(client, "owner@revise.io")
    return SimpleNamespace(client=client, owner=owner, store=store,
                           executions=executions, tmp_path=tmp_path, app_mod=app_mod)


def _signup(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/signup",
        json={"name": "Branch Owner", "email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seed_linear(store, user_id: str, count: int = 10, project_id: str | None = None):
    turns = []
    parent = None
    for number in range(1, count + 1):
        run = (
            store.create(user_id, f"question {number}", project_id)
            if parent is None
            else store.create_followup(user_id, f"question {number}", parent)
        )
        run.created_at = f"2026-07-20T00:00:{number:02d}+00:00"
        run.status = "delivered"
        run.report = f"answer {number}"
        run.tokens_used = number * 100
        run.cache_read_tokens = number * 1_000
        run.cache_write_tokens = number * 10
        store.persist(run)
        turns.append(run)
        parent = run
    return turns


def _attach(run, name: str, data: bytes) -> None:
    from api.run_inputs import persist_inputs

    asyncio.run(
        persist_inputs(
            run,
            [InputFile(name=name, modality="text", data=data, size=len(data))],
        )
    )


def _revise(client: TestClient, target_id: str, **data):
    payload = {"brief": "revised prompt", "reuseInputs": "false", **data}
    return client.post(f"/runs/{target_id}/revise", data=payload)


def test_revise_root_supersedes_all_ten_turns_in_the_same_session(env, monkeypatch):
    from core.memory import manager
    from foundation import MemoryItem, MemorySaver, MemoryStore

    turns = _seed_linear(env.store, env.owner["id"])
    durable = MemoryItem(
        memory_id="durable-1", store=MemoryStore.EPISODIC,
        content="saved fact survives", created_at=1784505660,
        saved_by=MemorySaver.MEMORY_CURATOR,
    )
    async def list_entries(user_id):
        assert user_id == env.owner["id"]
        return [durable]
    monkeypatch.setattr(manager, "list_entries", list_entries)
    session_id = turns[0].session_id

    response = _revise(
        env.client,
        turns[0].id,
        models='{"orchestrator": "claude-opus-4-8"}',
    )

    assert response.status_code == 201, response.text
    revised_id = response.json()["id"]
    revised = env.store.get(env.owner["id"], revised_id)
    assert revised.lineage_prefix is None
    assert revised.session_id == session_id
    assert revised.parent_run_id is None
    assert revised.session_models == {"orchestrator": "claude-opus-4-8"}
    assert revised.task is not None
    assert [run["id"] for run in env.client.get(f"/runs/{revised_id}/thread").json()] == [
        revised_id
    ]
    assert env.client.get(f"/runs/{turns[0].id}").status_code == 404
    assert env.client.get(f"/runs/{turns[0].id}/thread").status_code == 404
    visible = env.client.get("/runs").json()
    assert [run["id"] for run in visible] == [revised_id]
    assert {run["sessionId"] for run in visible} == {session_id}
    usage = env.client.get("/usage").json()
    assert usage["used"] == sum(
        turn.tokens_used for turn in turns
    )
    assert usage["cacheReadTokens"] == sum(turn.cache_read_tokens for turn in turns)
    assert usage["cacheWriteTokens"] == sum(turn.cache_write_tokens for turn in turns)
    assert [item["content"] for item in env.client.get("/memory").json()] == [
        "saved fact survives"
    ]
    assert len(env.store.list_for(env.owner["id"], include_superseded=True)) == 11


def test_turn_five_prefix_drives_rest_history_recall_and_file_reseeding(env):
    from api import run_driver

    project = env.client.post("/projects", json={"name": "Acme"}).json()
    turns = _seed_linear(env.store, env.owner["id"], project_id=project["id"])
    for index in (1, 4, 7):
        _attach(turns[index], f"turn-{index + 1}.txt", f"bytes {index + 1}".encode())
        env.store.persist(turns[index])

    response = _revise(env.client, turns[4].id)
    assert response.status_code == 201, response.text
    revised = env.store.get(env.owner["id"], response.json()["id"])

    expected_prefix = [turn.id for turn in turns[:4]]
    assert revised.lineage_prefix is None
    assert revised.parent_run_id == turns[3].id
    assert revised.session_id == turns[0].session_id
    assert revised.project_id == project["id"]
    assert [run["id"] for run in env.client.get(f"/runs/{revised.id}/thread").json()] == [
        *expected_prefix,
        revised.id,
    ]

    conversation = run_driver._build_conversation(revised)
    transcript = run_driver._build_transcript(revised)
    combined = " ".join(message["content"] for message in conversation)
    assert all(f"question {number}" in combined for number in range(1, 5))
    assert all(f"question {number}" not in combined for number in range(5, 11))
    assert [
        turn["user"].splitlines()[0] for turn in transcript
    ] == [f"question {number}" for number in range(1, 5)]

    gathered = asyncio.run(run_driver._gather_session_files(revised, []))
    assert [item.name for item in gathered] == ["turn-2.txt"]
    assert [run["id"] for run in env.client.get(f"/runs/{turns[0].id}/thread").json()] == [
        *expected_prefix,
        revised.id,
    ]
    assert env.client.get(f"/runs/{turns[4].id}").status_code == 404
    assert {run["id"] for run in env.client.get("/runs").json()} == {
        *expected_prefix,
        revised.id,
    }


def test_followup_on_revision_continues_the_truncated_session(env):
    turns = _seed_linear(env.store, env.owner["id"])
    revised_id = _revise(env.client, turns[4].id).json()["id"]
    revised = env.store.get(env.owner["id"], revised_id)

    followup_response = env.client.post(
        f"/runs/{revised_id}/followup",
        data={"brief": "continue revised branch"},
    )

    assert followup_response.status_code == 201, followup_response.text
    followup = env.store.get(env.owner["id"], followup_response.json()["id"])
    assert followup.lineage_prefix is None
    assert followup.session_id == revised.session_id
    expected = [turn.id for turn in turns[:4]] + [revised.id, followup.id]
    assert [run["id"] for run in env.client.get(f"/runs/{revised.id}/thread").json()] == expected
    assert [run["id"] for run in env.client.get(f"/runs/{followup.id}/thread").json()] == expected


def test_unknown_foreign_and_live_targets_do_not_disclose_or_create(env):
    unknown = _revise(env.client, "run_missing")
    assert unknown.status_code == 404

    foreign_client = TestClient(env.app_mod.app)
    foreign = _signup(foreign_client, "foreign@revise.io")
    foreign_target = _seed_linear(env.store, foreign["id"], count=1)[0]
    assert _revise(env.client, foreign_target.id).status_code == 404

    live = env.store.create(env.owner["id"], "still running")
    before = {run.id for run in env.store.list_for(env.owner["id"])}
    response = _revise(env.client, live.id)
    after = {run.id for run in env.store.list_for(env.owner["id"])}
    assert response.status_code == 409
    assert "finish" in response.json()["detail"].lower()
    assert after == before


def test_reuse_loads_authoritative_bytes_and_hides_integrity_metadata(env):
    target = _seed_linear(env.store, env.owner["id"], count=1)[0]
    _attach(target, "facts.txt", b"authoritative stored bytes")
    env.store.persist(target)
    public_inputs = env.client.get(f"/runs/{target.id}").json()["inputs"]
    assert "_sha256" not in public_inputs[0]

    response = env.client.post(
        f"/runs/{target.id}/revise",
        data={"brief": "use the same file"},
    )

    assert response.status_code == 201, response.text
    revised, input_files = env.executions[-1]
    assert revised.id == response.json()["id"]
    assert [(item.name, item.data) for item in input_files] == [
        ("facts.txt", b"authoritative stored bytes")
    ]
    assert env.client.get(f"/runs/{target.id}").status_code == 404


def test_legacy_unhashed_target_input_reuses_namespace_bound_server_blob(env):
    target = _seed_linear(env.store, env.owner["id"], count=1)[0]
    _attach(target, "legacy.txt", b"pre-hash authoritative bytes")
    target.inputs[0].pop("_sha256")
    env.store.persist(target)

    response = env.client.post(
        f"/runs/{target.id}/revise",
        data={"brief": "reuse the legacy file"},
    )

    assert response.status_code == 201, response.text
    assert [(item.name, item.data) for item in env.executions[-1][1]] == [
        ("legacy.txt", b"pre-hash authoritative bytes")
    ]


@pytest.mark.parametrize("fault", ["metadata_only", "missing", "corrupt"])
def test_unreusable_target_input_fails_before_run_creation(env, fault):
    target = _seed_linear(env.store, env.owner["id"], count=1)[0]
    if fault == "metadata_only":
        target.inputs = [
            {
                "name": "claimed.txt",
                "modality": "text",
                "size": 4,
                "data": "evil",
            }
        ]
    else:
        _attach(target, "stored.txt", b"safe bytes")
        artifact_path = (
            Path(env.tmp_path)
            / "artifacts"
            / f"in_{target.id}"
            / "stored.txt"
        )
        if fault == "missing":
            artifact_path.unlink()
        else:
            artifact_path.write_bytes(b"evil bytes")
    env.store.persist(target)
    before = {run.id for run in env.store.list_for(env.owner["id"])}
    execution_count = len(env.executions)

    response = env.client.post(
        f"/runs/{target.id}/revise",
        data={"brief": "reuse broken input"},
    )

    assert response.status_code == 409
    assert "replacement" in response.json()["detail"].lower()
    assert {run.id for run in env.store.list_for(env.owner["id"])} == before
    assert len(env.executions) == execution_count


def test_model_and_upload_preflights_leave_chat_unchanged(env, monkeypatch):
    turns = _seed_linear(env.store, env.owner["id"], count=3)
    before = [run.id for run in env.store.session_turns(env.owner["id"], turns[0].session_id)]

    malformed_model = env.client.post(
        f"/runs/{turns[1].id}/revise",
        data={
            "brief": "edited prompt",
            "reuseInputs": "false",
            "models": "not-json",
        },
    )

    async def reject(_name, _data):
        return None, "upload rejected"

    monkeypatch.setattr("api.run_requests.upload_scan.scan_upload", reject)
    rejected_upload = env.client.post(
        f"/runs/{turns[1].id}/revise",
        data={"brief": "edited prompt"},
        files={"files": ("unsafe.txt", b"unsafe", "text/plain")},
    )

    assert malformed_model.status_code == 422
    assert rejected_upload.status_code == 422
    assert [run.id for run in env.store.session_turns(
        env.owner["id"], turns[0].session_id
    )] == before
    assert env.client.get(f"/runs/{turns[1].id}").status_code == 200


def test_metadata_cannot_redirect_reuse_to_another_run_blob(env):
    source, target = _seed_linear(env.store, env.owner["id"], count=2)
    _attach(source, "source.txt", b"do not inject")
    env.store.persist(source)
    target.inputs = [dict(source.inputs[0])]
    env.store.persist(target)

    response = env.client.post(
        f"/runs/{target.id}/revise",
        data={"brief": "attempt redirected reuse"},
    )

    assert response.status_code == 409
    assert not env.executions


def test_replacements_supersede_reuse_and_false_allows_no_current_inputs(env, monkeypatch):
    replacement_target = _seed_linear(env.store, env.owner["id"], count=1)[0]
    replacement_target.inputs = [
        {"name": "missing.txt", "modality": "text", "size": 2}
    ]
    env.store.persist(replacement_target)
    no_input_target = _seed_linear(env.store, env.owner["id"], count=1)[0]
    no_input_target.inputs = [
        {"name": "also-missing.txt", "modality": "text", "size": 2}
    ]
    env.store.persist(no_input_target)
    scanned = []

    async def admit(name, data):
        scanned.append((name, data))
        return InputFile(name=name, modality="text", data=data, size=len(data)), None

    monkeypatch.setattr("api.run_requests.upload_scan.scan_upload", admit)
    replacement = env.client.post(
        f"/runs/{replacement_target.id}/revise",
        data={"brief": "replace it"},
        files={"files": ("replacement.txt", b"fresh bytes", "text/plain")},
    )
    no_inputs = env.client.post(
        f"/runs/{no_input_target.id}/revise",
        data={"brief": "use no file", "reuseInputs": "false"},
    )

    assert replacement.status_code == 201, replacement.text
    assert scanned == [("replacement.txt", b"fresh bytes")]
    assert [item.data for item in env.executions[-2][1]] == [b"fresh bytes"]
    assert no_inputs.status_code == 201, no_inputs.text
    assert env.executions[-1][1] == []


def test_live_descendant_is_cancelled_and_cannot_reappear(env):
    class LiveTask:
        cancelled = False

        def done(self):
            return False

        def cancel(self):
            self.cancelled = True

    target = _seed_linear(env.store, env.owner["id"], count=1)[0]
    descendant = env.store.create_followup(env.owner["id"], "live descendant", target)
    descendant.status = "running"
    descendant.task = LiveTask()

    response = _revise(env.client, target.id)

    assert response.status_code == 201, response.text
    assert descendant.superseded is True
    assert descendant.cancel_requested is True
    assert descendant.task.cancelled is True
    descendant.status = "cancelled"
    env.store.persist(descendant)
    assert env.store.get(env.owner["id"], descendant.id) is None
    assert descendant.id not in {
        run.id for run in env.store.list_for(env.owner["id"])
    }
    assert descendant.id in {
        run.id
        for run in env.store.list_for(env.owner["id"], include_superseded=True)
    }


def test_revised_task_is_registered_before_atomic_truncation_returns(env):
    turns = _seed_linear(env.store, env.owner["id"], count=3)

    response = _revise(env.client, turns[1].id)

    revised = env.store.get(env.owner["id"], response.json()["id"])
    assert revised.task is not None
    assert env.store.get(env.owner["id"], turns[1].id) is None
    assert [run.id for run in env.store.session_turns(env.owner["id"], revised.session_id)] == [
        turns[0].id,
        revised.id,
    ]


def test_missing_or_foreign_stored_prefix_fails_closed(env):
    from api.run_state import RunState

    foreign_client = TestClient(env.app_mod.app)
    foreign = _signup(foreign_client, "prefix-foreign@revise.io")
    foreign_turn = _seed_linear(env.store, foreign["id"], count=1)[0]

    for branch_id, prefix_id in (
        ("run_missing_branch", "run_missing"),
        ("run_foreign_branch", foreign_turn.id),
    ):
        branch = RunState(
            id=branch_id,
            user_id=env.owner["id"],
            title="branch",
            brief="branch",
            status="delivered",
            session_id=branch_id,
            lineage_prefix=[prefix_id],
        )
        env.store._runs[branch.id] = branch
        response = env.client.get(f"/runs/{branch.id}/thread")
        assert response.status_code == 409
        assert "lineage" in response.json()["detail"].lower()


def test_malformed_persisted_prefix_fails_closed(env):
    branch = env.store.create(env.owner["id"], "branch")
    branch.status = "delivered"
    branch.lineage_prefix = []
    env.store.persist(branch)
    from api import auth

    with auth._db() as db:
        db.execute(
            "UPDATE runs SET lineage_prefix_json='{}' WHERE id=?",
            (branch.id,),
        )

    response = env.client.get(f"/runs/{branch.id}/thread")

    assert response.status_code == 409
    assert "lineage" in response.json()["detail"].lower()


def test_revised_execution_keeps_project_scoped_wiki_hydration(env, monkeypatch):
    """The normal execute seam receives the target's unchanged project ID."""
    from api import run_driver

    project = env.client.post("/projects", json={"name": "Hydration scope"}).json()
    target = _seed_linear(
        env.store, env.owner["id"], count=1, project_id=project["id"]
    )[0]
    revised = env.store.create_revision(env.owner["id"], "edited", target)
    seen = []

    def fetch_wiki(user_id, project_id):
        seen.append((user_id, project_id))
        return []

    async def fake_pipeline_run(brief, **kwargs):
        flow = Flow.new(brief, session_id=kwargs["session_id"],
                        user_id=kwargs["user_id"], trace_id=kwargs["trace_id"])
        flow.ctx.decision_log = kwargs["decision_log"]
        kwargs["prepare"](flow)
        flow.ctx.orchestrator_response = SimpleNamespace(
            presentation="chat", metadata={}, message=""
        )
        flow.ctx.final_response = "done"
        return flow

    monkeypatch.setattr(run_driver.auth, "fetch_wiki", fetch_wiki)
    monkeypatch.setattr(run_driver, "build_model_overrides", lambda *args: {})
    monkeypatch.setattr(run_driver.pipeline, "run", fake_pipeline_run)
    asyncio.run(run_driver.execute(revised, []))

    assert seen == [(env.owner["id"], project["id"])]
