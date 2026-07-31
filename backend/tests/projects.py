"""
Projects: a project = a client / body of work; runs + memory scope to it. Covers the
data layer (auth.project_*, the store's project filter + cascade), wiki/memory scoping,
and the routes (CRUD + ownership 422) — all on a throwaway DB, no pipeline.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from api import config, run_store
    import api.runs as runs_mod
    from core.memory import manager

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    store = run_store.RunStore()                       # fresh store: no cross-test live runs
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)      # the routes read runs.STORE
    async def empty_memory(_user_id):
        return []
    monkeypatch.setattr(manager, "list_entries", empty_memory)
    yield


def test_project_data_layer_scopes_and_cascades(db):
    from api import auth
    from api.run_store import STORE

    user = auth.create_user("a@b.com", "A", "password123")
    other = auth.create_user("c@d.com", "C", "password123")

    proj = auth.project_create(user.id, "Acme", "amber")
    assert auth.project_get(user.id, proj["id"])["name"] == "Acme"
    assert auth.project_get(other.id, proj["id"]) is None          # ownership-scoped

    run = STORE.create(user.id, "do a thing", proj["id"])
    run.status = "delivered"
    STORE.persist(run)
    auth.wiki_create(user.id, "client note", "Acme is a client", project_id=proj["id"])
    auth.wiki_create(user.id, "global note", "I am a designer")    # unscoped (no project)

    assert [r.id for r in STORE.list_for(user.id, proj["id"])] == [run.id]
    assert STORE.list_for(user.id, "proj_nope") == []
    assert [w["title"] for w in auth.wiki_list(user.id, proj["id"])] == ["client note"]
    assert [w["title"] for w in auth.fetch_wiki(user.id, proj["id"])] == ["client note"]
    assert len(auth.wiki_list(user.id)) == 2                       # account-wide (no project arg)

    assert auth.project_rename(user.id, proj["id"], "Acme Corp")["name"] == "Acme Corp"
    assert auth.project_rename(other.id, proj["id"], "x") is None  # not theirs

    removed = STORE.delete_project(user.id, proj["id"])
    assert removed == 1
    assert auth.project_get(user.id, proj["id"]) is None
    assert STORE.get(user.id, run.id) is None                      # the run cascaded away
    assert [w["title"] for w in auth.wiki_list(user.id)] == ["global note"]  # project wiki gone, account wiki kept


def test_project_list_is_newest_activity_first(db):
    from api import auth
    from api.run_store import STORE

    user = auth.create_user("a@b.com", "A", "password123")
    p1 = auth.project_create(user.id, "first")
    p2 = auth.project_create(user.id, "second")
    r = STORE.create(user.id, "x", p1["id"])          # a run in p1 makes it the most recently active
    r.status = "delivered"
    STORE.persist(r)
    assert [p["id"] for p in auth.project_list(user.id)][0] == p1["id"]   # activity beats creation order


def test_project_routes_crud_seed_and_ownership(db):
    from api.app import app

    client = TestClient(app)
    client.post("/auth/signup", json={"name": "Ann", "email": "ann@x.com", "password": "password123"})

    r = client.post("/projects", json={"name": "Globex", "color": "amber", "seedFacts": "Globex builds widgets"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["name"] == "Globex" and r.json()["color"] == "amber" and r.json()["createdAt"]

    assert [p["id"] for p in client.get("/projects").json()] == [pid]

    mem = client.get(f"/memory?projectId={pid}").json()
    assert any("Client: Globex" in m["title"] for m in mem)        # seedFacts became a project wiki entry
    assert mem and all(m["projectId"] == pid for m in mem)

    # a write into an unknown/other-user project is rejected (never trust a body id)
    assert client.post("/memory", json={"tier": "wiki", "title": "t", "content": "c", "projectId": "proj_nope"}).status_code == 422
    ok = client.post("/memory", json={"tier": "wiki", "title": "t", "content": "c", "projectId": pid})
    assert ok.status_code == 201 and ok.json()["projectId"] == pid

    assert client.patch(f"/projects/{pid}", json={"name": "Globex Inc"}).json()["name"] == "Globex Inc"

    assert client.delete(f"/projects/{pid}").status_code == 204    # cascade
    assert client.get("/projects").json() == []
    assert client.get(f"/memory?projectId={pid}").json() == []     # its wiki went with it


def test_wiki_upload_scopes_to_project(db):
    from api.app import app

    client = TestClient(app)
    client.post("/auth/signup", json={"name": "Bo", "email": "bo@x.com", "password": "password123"})
    pid = client.post("/projects", json={"name": "Initech"}).json()["id"]

    # upload a markdown wiki file INTO the project — projectId is a multipart FORM field
    r = client.post(
        "/memory/upload",
        files=[("files", ("notes.md", b"Initech notes here", "text/markdown"))],
        data={"projectId": pid},
    )
    assert r.status_code == 201
    assert r.json() and all(e["projectId"] == pid for e in r.json())     # tagged to the project

    assert any("notes" in m["title"].lower() for m in client.get(f"/memory?projectId={pid}").json())
    other = client.post("/projects", json={"name": "Other"}).json()["id"]
    assert client.get(f"/memory?projectId={other}").json() == []         # does NOT leak to other projects

    bad = client.post("/memory/upload",
                      files=[("files", ("x.md", b"x", "text/markdown"))],
                      data={"projectId": "proj_nope"})
    assert bad.status_code == 422                                        # unknown project rejected


def test_wiki_upload_scopes_via_query_param(db):
    from api.app import app

    client = TestClient(app)
    client.post("/auth/signup", json={"name": "Cy", "email": "cy@x.com", "password": "password123"})
    pid = client.post("/projects", json={"name": "Hooli"}).json()["id"]

    # the frontend may send projectId as a QUERY param (like its other scoped calls), not a form field
    r = client.post(
        f"/memory/upload?projectId={pid}",
        files=[("files", ("doc.md", b"Hooli doc", "text/markdown"))],
    )
    assert r.status_code == 201
    assert r.json() and all(e["projectId"] == pid for e in r.json())   # scoped via the query param
    other = client.post("/projects", json={"name": "Pied"}).json()["id"]
    assert client.get(f"/memory?projectId={other}").json() == []       # stays isolated, no leak


def test_inferred_memory_can_be_deleted(db, monkeypatch):
    from api.app import app
    from core.memory import manager
    from foundation import MemoryItem, MemoryKind, MemorySaver, MemoryStore

    client = TestClient(app)
    me = client.post("/auth/signup", json={"name": "Ed", "email": "ed@x.com", "password": "password123"}).json()

    entries = [
        MemoryItem(
            memory_id="point-1", store=MemoryStore.EPISODIC,
            content="fact one", created_at=1781740801,
            saved_by=MemorySaver.MEMORY_CURATOR,
        ),
        MemoryItem(
            memory_id="point-2", store=MemoryStore.EPISODIC,
            content="fact two (outdated)", created_at=1781740802,
            kind=MemoryKind.ASSUMPTION, rationale="turn outcome",
            saved_by=MemorySaver.MEMORY_CURATOR, session_id="s1", trace_id="t1",
        ),
    ]
    async def list_entries(user_id):
        assert user_id == me["id"]
        return list(entries)
    async def delete_entry(user_id, memory_id):
        assert user_id == me["id"]
        for item in list(entries):
            if item.memory_id == memory_id:
                entries.remove(item)
                return True
        return False
    monkeypatch.setattr(manager, "list_entries", list_entries)
    monkeypatch.setattr(manager, "delete_entry", delete_entry)

    episodic = [m for m in client.get("/memory").json() if m["tier"] == "episodic"]
    assert len(episodic) == 2
    outdated = next(m for m in episodic if "outdated" in m["content"])
    assert outdated["id"] == "point-2"
    assert outdated["savedBy"] == "memory_curator"
    assert outdated["rationale"] == "turn outcome"
    assert outdated["kind"] == "assumption"
    assert outdated["sessionId"] == "s1"
    assert outdated["traceId"] == "t1"
    assert outdated["updatedAt"]

    assert client.delete(f"/memory/{outdated['id']}").status_code == 204
    after = [m for m in client.get("/memory").json() if m["tier"] == "episodic"]
    assert [m["content"] for m in after] == ["fact one"]              # only the outdated one removed

    assert client.delete("/memory/point-9").status_code == 404
