"""GET /memory/hydration-preview — a read-only DRY-RUN of MemoryPort.hydrate for a
draft brief (the frontend's real-ranking memory panel, proposals/
frontend_hydration_preview_endpoint.md). Hermetic: manager.hydrate is faked; pins
the same-door scoping (user_id from the session, never the request), the
MemoryEntry+score shape, wiki id resolution, the cap, and the never-5xx posture."""

import pytest
from fastapi.testclient import TestClient

from foundation import HydrationPackage, MemoryItem, MemoryStore


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from api import config, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)
    yield


def _client_with_user(name="Pia", email="pia@x.com"):
    from api.app import app

    client = TestClient(app)
    me = client.post("/auth/signup", json={"name": name, "email": email, "password": "password123"}).json()
    return client, me


def _fake_hydrate(monkeypatch, package_or_exc):
    """Patch the MemoryPort door; record every HydrationRequest it receives."""
    from core.memory import manager

    seen = []

    async def hydrate(request):
        seen.append(request)
        if isinstance(package_or_exc, Exception):
            raise package_or_exc
        return package_or_exc

    monkeypatch.setattr(manager, "hydrate", hydrate)
    return seen


def test_preview_requires_auth(db):
    from api.app import app

    assert TestClient(app).get("/memory/hydration-preview?brief=who is acme").status_code == 401


def test_preview_scopes_to_the_session_user_and_maps_the_shape(db, monkeypatch):
    client, me = _client_with_user()
    wiki = client.post(
        "/memory", json={"tier": "wiki", "title": "Acme brief style", "content": "Keep Acme reports to one page"}
    ).json()

    items = [
        MemoryItem(store=MemoryStore.WIKI, content="Keep Acme reports to one page", score=0.9, trust=3),
        MemoryItem(store=MemoryStore.SEMANTIC, content="Acme sells solar inverters\nsecond line", score=0.7, trust=2),
    ]
    seen = _fake_hydrate(monkeypatch, HydrationPackage(items=items))

    got = client.get("/memory/hydration-preview?brief=what do we know about acme").json()

    # scoping: user_id comes from the SESSION, the brief from the query — same door
    assert len(seen) == 1 and seen[0].user_id == me["id"]
    assert seen[0].normalized.content == "what do we know about acme"
    assert ("Acme brief style", "Keep Acme reports to one page") in seen[0].wiki

    # shape: MemoryEntry + score; the wiki hit resolves to its REAL entry
    assert [e["tier"] for e in got] == ["wiki", "semantic"]
    assert got[0]["id"] == wiki["id"] and got[0]["title"] == "Acme brief style"
    assert got[0]["score"] == 0.9
    # learned-tier hit: synthetic id + first-line title
    assert got[1]["id"] == "preview_1" and got[1]["title"] == "Acme sells solar inverters"
    assert got[1]["score"] == 0.7 and got[1]["content"].startswith("Acme sells")


def test_preview_caps_items_and_clamps_scores(db, monkeypatch):
    client, _ = _client_with_user(email="cap@x.com")
    items = [
        MemoryItem(store=MemoryStore.SEMANTIC, content=f"fact {n}", score=2.0 - n, trust=2)
        for n in range(12)
    ]
    _fake_hydrate(monkeypatch, HydrationPackage(items=items))

    got = client.get("/memory/hydration-preview?brief=long enough brief").json()
    assert len(got) == 8                                   # capped for the panel
    assert got[0]["score"] == 1.0                          # clamped into 0..1
    assert all(0.0 <= e["score"] <= 1.0 for e in got)


def test_preview_short_brief_skips_hydration(db, monkeypatch):
    client, _ = _client_with_user(email="short@x.com")
    seen = _fake_hydrate(monkeypatch, HydrationPackage(items=[]))

    assert client.get("/memory/hydration-preview?brief=hi").json() == []
    assert client.get("/memory/hydration-preview").json() == []
    assert seen == []                                      # never hit the door


def test_preview_never_5xxs(db, monkeypatch):
    client, _ = _client_with_user(email="fault@x.com")

    _fake_hydrate(monkeypatch, RuntimeError("qdrant down"))
    r = client.get("/memory/hydration-preview?brief=what about acme")
    assert r.status_code == 200 and r.json() == []         # fault -> empty preview

    _fake_hydrate(monkeypatch, HydrationPackage(degraded=True, notes="down"))
    r = client.get("/memory/hydration-preview?brief=what about acme")
    assert r.status_code == 200 and r.json() == []         # degraded -> empty preview
