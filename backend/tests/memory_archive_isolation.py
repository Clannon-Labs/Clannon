"""HTTP tenant-isolation proof for the durable memory archive.

Uses two authenticated clients, fresh SQLite state, and an owner-scoped fake
Memory Manager. No Qdrant or pipeline process is required.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from foundation import MemoryItem, MemoryStore


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from api import app as app_mod, config, run_driver, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "memory-archive.db"))
    monkeypatch.setattr(config, "DEFAULT_PLAN", "pro")
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(run_driver, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)
    app_mod._auth_attempts.clear()
    return SimpleNamespace(app=app_mod.app)


def _signup(app, email: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    response = client.post(
        "/auth/signup",
        json={"name": "Archive User", "email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return client, response.json()


def _inferred_entries(owner: str) -> list[MemoryItem]:
    return [
        MemoryItem(
            memory_id=f"{owner}-semantic",
            store=MemoryStore.SEMANTIC,
            content=f"{owner} private semantic fact",
        ),
        MemoryItem(
            memory_id=f"{owner}-episodic",
            store=MemoryStore.EPISODIC,
            content=f"{owner} private episode",
        ),
        MemoryItem(
            memory_id=f"{owner}-procedural",
            store=MemoryStore.PROCEDURAL,
            content=f"{owner} private procedure",
        ),
    ]


@pytest.fixture()
def archive(env, monkeypatch):
    from core.memory import manager

    alice, alice_user = _signup(env.app, "alice-archive@example.com")
    bob, bob_user = _signup(env.app, "bob-archive@example.com")
    alice_wiki = alice.post(
        "/memory",
        json={"tier": "wiki", "title": "Alice wiki", "content": "alice private wiki"},
    ).json()
    bob_wiki = bob.post(
        "/memory",
        json={"tier": "wiki", "title": "Bob wiki", "content": "bob private wiki"},
    ).json()
    entries_by_user = {
        alice_user["id"]: _inferred_entries("alice"),
        bob_user["id"]: _inferred_entries("bob"),
    }
    list_calls: list[str] = []
    delete_calls: list[tuple[str, str]] = []

    async def list_entries(user_id: str) -> list[MemoryItem]:
        list_calls.append(user_id)
        return list(entries_by_user.get(user_id, ()))

    async def delete_entry(user_id: str, memory_id: str) -> bool:
        delete_calls.append((user_id, memory_id))
        owned = entries_by_user.get(user_id, [])
        match = next((item for item in owned if item.memory_id == memory_id), None)
        if match is None:
            return False
        owned.remove(match)
        return True

    monkeypatch.setattr(manager, "list_entries", list_entries)
    monkeypatch.setattr(manager, "delete_entry", delete_entry)
    return SimpleNamespace(
        alice=alice,
        alice_user=alice_user,
        alice_wiki=alice_wiki,
        bob=bob,
        bob_user=bob_user,
        bob_wiki=bob_wiki,
        entries_by_user=entries_by_user,
        list_calls=list_calls,
        delete_calls=delete_calls,
    )


def test_memory_archive_list_never_returns_another_users_entries(archive):
    alice_archive = archive.alice.get("/memory")
    bob_archive = archive.bob.get("/memory")

    assert alice_archive.status_code == bob_archive.status_code == 200
    assert {entry["id"] for entry in alice_archive.json()} == {
        archive.alice_wiki["id"],
        "alice-semantic",
        "alice-episodic",
        "alice-procedural",
    }
    assert {entry["id"] for entry in bob_archive.json()} == {
        archive.bob_wiki["id"],
        "bob-semantic",
        "bob-episodic",
        "bob-procedural",
    }
    assert {entry["tier"] for entry in alice_archive.json()} == {
        "wiki",
        "semantic",
        "episodic",
        "procedural",
    }
    assert {entry["tier"] for entry in bob_archive.json()} == {
        "wiki",
        "semantic",
        "episodic",
        "procedural",
    }
    assert archive.list_calls == [
        archive.alice_user["id"],
        archive.bob_user["id"],
    ]


def test_memory_archive_foreign_delete_matches_unknown_and_preserves_owner(archive):
    foreign = archive.alice.delete("/memory/bob-semantic")
    unknown = archive.alice.delete("/memory/does-not-exist")
    assert (
        foreign.status_code,
        foreign.headers["content-type"],
        foreign.content,
    ) == (
        unknown.status_code,
        unknown.headers["content-type"],
        unknown.content,
    ) == (404, "application/json", b'{"detail":"Memory entry not found."}')

    assert archive.delete_calls == [
        (archive.alice_user["id"], "bob-semantic"),
        (archive.alice_user["id"], "does-not-exist"),
    ]
    assert {
        item.memory_id for item in archive.entries_by_user[archive.bob_user["id"]]
    } == {
        "bob-semantic",
        "bob-episodic",
        "bob-procedural",
    }
    assert "bob-semantic" in {
        entry["id"] for entry in archive.bob.get("/memory").json()
    }
