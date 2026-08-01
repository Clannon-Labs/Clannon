"""Server-owned plan enforcement for every API/runtime memory path.

Hermetic proof: fresh SQLite + RunStore, authenticated HTTP clients, and a fake
Memory Manager that deliberately ignores requested tiers. The API must enforce
entitlements even when that dependency returns too much.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from foundation import Flow, HydrationPackage, MemoryItem, MemoryStore


PLAN_TIERS = {
    "free": (MemoryStore.EPISODIC,),
    "starter": (MemoryStore.EPISODIC, MemoryStore.WIKI),
    "pro": (
        MemoryStore.EPISODIC,
        MemoryStore.WIKI,
        MemoryStore.SEMANTIC,
        MemoryStore.PROCEDURAL,
    ),
    "corrupt-plan": (),
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from api import app as app_mod, config, run_driver, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "entitlements.db"))
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(run_driver, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)
    app_mod._auth_attempts.clear()
    return SimpleNamespace(app=app_mod.app, store=store)


def _set_plan(user_id: str, plan: str) -> None:
    from api import auth

    with auth._db() as db:
        db.execute("UPDATE users SET plan=? WHERE id=?", (plan, user_id))


def _signup(app, email: str, plan: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    response = client.post(
        "/auth/signup",
        json={"name": "Plan User", "email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    user = response.json()
    _set_plan(user["id"], plan)
    return client, user


def _all_manager_items(prefix: str = "item") -> list[MemoryItem]:
    return [
        MemoryItem(memory_id=f"{prefix}-wiki", store=MemoryStore.WIKI, content="Private wiki"),
        MemoryItem(
            memory_id=f"{prefix}-episodic",
            store=MemoryStore.EPISODIC,
            content="Episodic continuity",
        ),
        MemoryItem(
            memory_id=f"{prefix}-semantic",
            store=MemoryStore.SEMANTIC,
            content="Paid semantic fact",
        ),
        MemoryItem(
            memory_id=f"{prefix}-procedural",
            store=MemoryStore.PROCEDURAL,
            content="Paid procedure",
        ),
    ]


def test_plan_mapping_comes_from_central_config_and_corruption_fails_closed(monkeypatch):
    from api import config
    from api.memory_entitlements import allowed_memory_tiers

    for plan, expected in PLAN_TIERS.items():
        assert allowed_memory_tiers(plan) == expected

    original = config.PLANS
    monkeypatch.setattr(
        config,
        "PLANS",
        [
            *original,
            {"id": "bad-tier", "memoryTiers": ["episodic", "not-a-tier"]},
            {"id": "working", "memoryTiers": ["working"]},
            {"id": "wrong-shape", "memoryTiers": "episodic"},
            {"id": "duplicate", "memoryTiers": ["episodic", "episodic"]},
            {"id": "free", "memoryTiers": ["episodic"]},
        ],
    )
    for plan in (None, "", "free", "bad-tier", "working", "wrong-shape", "duplicate"):
        assert allowed_memory_tiers(plan) == ()


@pytest.mark.parametrize("plan", list(PLAN_TIERS))
def test_memory_list_returns_only_plan_tiers_even_when_manager_overreturns(
    env, monkeypatch, plan
):
    from api import auth
    from core.memory import manager

    client, user = _signup(env.app, f"list-{plan}@example.com", plan)
    auth.wiki_create(user["id"], "Private wiki", "Private wiki")

    async def list_every_tier(user_id: str):
        assert user_id == user["id"]
        return _all_manager_items(plan)

    monkeypatch.setattr(manager, "list_entries", list_every_tier)
    response = client.get("/memory")

    assert response.status_code == 200
    assert {entry["tier"] for entry in response.json()} == {
        tier.value for tier in PLAN_TIERS[plan]
    }


@pytest.mark.parametrize("plan", list(PLAN_TIERS))
def test_preview_passes_exact_tiers_omits_locked_wiki_and_filters_faulty_reply(
    env, monkeypatch, plan
):
    from api import auth
    from core.memory import manager

    client, user = _signup(env.app, f"preview-{plan}@example.com", plan)
    auth.wiki_create(user["id"], "Private wiki", "Private wiki")
    requests = []

    async def ignore_requested_tiers(request):
        requests.append(request)
        return HydrationPackage(items=_all_manager_items(plan))

    monkeypatch.setattr(manager, "hydrate", ignore_requested_tiers)
    response = client.get("/memory/hydration-preview?brief=what should I remember")

    assert response.status_code == 200
    assert len(requests) == 1
    assert requests[0].allowed_tiers == PLAN_TIERS[plan]
    assert bool(requests[0].wiki) is (MemoryStore.WIKI in PLAN_TIERS[plan])
    assert {entry["tier"] for entry in response.json()} == {
        tier.value for tier in PLAN_TIERS[plan]
    }


@pytest.mark.parametrize("plan", list(PLAN_TIERS))
def test_real_execute_context_uses_current_server_plan_before_prefetch(
    env, monkeypatch, plan
):
    from api import auth, run_driver

    user = auth.create_user(f"run-{plan}@example.com", "Runner", "password123")
    _set_plan(user.id, plan)
    auth.wiki_create(user.id, "Private wiki", "Pipeline wiki content")
    run = env.store.create(user.id, "remember this plan")
    captured = []

    async def no_inputs(_run, _files):
        return None

    async def no_session_files(_run, _files):
        return []

    async def stop_after_prepare(raw_input, **kwargs):
        flow = Flow.new(
            raw_input,
            session_id=kwargs["session_id"],
            user_id=kwargs["user_id"],
            trace_id=kwargs["trace_id"],
        )
        kwargs["prepare"](flow)
        captured.append(flow.ctx)
        raise RuntimeError("stop after entitlement capture")

    monkeypatch.setattr(run_driver, "persist_inputs", no_inputs)
    monkeypatch.setattr(run_driver, "_gather_session_files", no_session_files)
    monkeypatch.setattr(run_driver, "build_model_overrides", lambda *_a, **_k: {})
    monkeypatch.setattr(run_driver.pipeline, "run", stop_after_prepare)

    asyncio.run(run_driver.execute(run))

    assert len(captured) == 1
    assert captured[0].memory_allowed_tiers == PLAN_TIERS[plan]
    assert bool(captured[0].wiki_entries) is (MemoryStore.WIKI in PLAN_TIERS[plan])


def test_free_wiki_mutations_are_403_and_persist_nothing(env):
    from api import auth

    client, user = _signup(env.app, "free-writes@example.com", "free")
    project = client.post("/projects", json={"name": "Allowed empty project"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    locked = auth.wiki_create(user["id"], "Locked", "Original", project_id)
    before_wiki = auth.wiki_list(user["id"])
    before_projects = auth.project_list(user["id"])

    create = client.post(
        "/memory",
        json={
            "tier": "wiki",
            "title": "Bypass create",
            "content": "must not persist",
            "projectId": project_id,
        },
    )
    update = client.put(
        f"/memory/{locked['id']}",
        json={"tier": "wiki", "title": "Bypass update", "content": "changed"},
    )
    upload = client.post(
        "/memory/upload",
        files=[("files", ("bypass.md", b"must not persist", "text/markdown"))],
        data={"projectId": project_id},
    )
    seed = client.post(
        "/projects",
        json={"name": "Bypass seed", "seedFacts": "must not persist"},
    )

    assert [create.status_code, update.status_code, upload.status_code, seed.status_code] == [
        403,
        403,
        403,
        403,
    ]
    assert auth.wiki_list(user["id"]) == before_wiki
    assert auth.project_list(user["id"]) == before_projects


def test_locked_memory_can_still_be_deleted_after_downgrade(env, monkeypatch):
    from api import auth
    from core.memory import manager

    client, user = _signup(env.app, "downgraded-delete@example.com", "free")
    wiki = auth.wiki_create(user["id"], "Locked wiki", "remove me")
    inferred = _all_manager_items("locked")

    async def delete_owned(user_id: str, memory_id: str) -> bool:
        if user_id != user["id"]:
            return False
        match = next((item for item in inferred if item.memory_id == memory_id), None)
        if match is None:
            return False
        inferred.remove(match)
        return True

    monkeypatch.setattr(manager, "delete_entry", delete_owned)

    assert client.delete(f"/memory/{wiki['id']}").status_code == 204
    assert auth.wiki_list(user["id"]) == []
    assert client.delete("/memory/locked-semantic").status_code == 204
    assert all(item.memory_id != "locked-semantic" for item in inferred)


def test_foreign_memory_and_project_ids_keep_non_disclosing_errors(env, monkeypatch):
    from api import auth
    from core.memory import manager

    alice, alice_user = _signup(env.app, "alice-entitlement@example.com", "starter")
    bob, bob_user = _signup(env.app, "bob-entitlement@example.com", "starter")
    project = alice.post("/projects", json={"name": "Alice private"}).json()
    wiki = alice.post(
        "/memory",
        json={"tier": "wiki", "title": "Alice", "content": "secret"},
    ).json()

    async def never_delete_foreign(user_id: str, memory_id: str) -> bool:
        assert user_id == bob_user["id"]
        return False

    monkeypatch.setattr(manager, "delete_entry", never_delete_foreign)
    foreign = bob.delete("/memory/alice-inferred")
    unknown = bob.delete("/memory/unknown-inferred")

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    assert bob.put(
        f"/memory/{wiki['id']}",
        json={"tier": "wiki", "title": "takeover", "content": "takeover"},
    ).status_code == 404
    assert bob.post(
        "/memory",
        json={
            "tier": "wiki",
            "title": "foreign project",
            "content": "no",
            "projectId": project["id"],
        },
    ).status_code == 422
    assert auth.wiki_list(alice_user["id"])[0]["content"] == "secret"
