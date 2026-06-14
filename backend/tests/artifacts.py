"""Output-artifact capture + the local artifact store."""

import asyncio
from types import SimpleNamespace as NS

import pytest

from foundation import ArtifactRef, ArtifactStore, VrakshaContext
from core.artifacts import LocalArtifactStore
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.support import ExpertEnv, SkillBook


def test_local_store_roundtrip(tmp_path):
    store = LocalArtifactStore(base_dir=tmp_path)
    assert isinstance(store, ArtifactStore)

    async def body():
        ref = await store.put("run1", "report.md", b"# hi")
        assert isinstance(ref, ArtifactRef)
        assert ref.name == "report.md" and ref.mime == "text/markdown" and ref.size == 4
        assert await store.get(ref.id) == b"# hi"
        assert [r.name for r in await store.list("run1")] == ["report.md"]
        assert await store.list("other") == []
    asyncio.run(body())


@pytest.mark.parametrize("bad", ["", ".", "..", "x\x00y"])
def test_store_rejects_invalid_names(tmp_path, bad):
    store = LocalArtifactStore(base_dir=tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(store.put("run1", bad, b"x"))


def test_store_flattens_pathy_names_safely(tmp_path):
    # a path-y name is confined to its basename under the run dir, never escaping
    store = LocalArtifactStore(base_dir=tmp_path)

    async def body():
        ref = await store.put("run1", "../../etc/passwd", b"x")
        assert ref.name == "passwd"
        assert (tmp_path / "run1" / "passwd").exists()
        assert not (tmp_path.parent / "passwd").exists()
    asyncio.run(body())


class _WS:
    """Minimal workspace stand-in exposing read_bytes."""
    def __init__(self, files):
        self._f = files
    async def read_bytes(self, p):
        if p not in self._f:
            raise FileNotFoundError(p)
        return self._f[p]


def _env(tmp_path, ws):
    return ExpertEnv(module_dir=tmp_path, model_role="code", skills=SkillBook(tmp_path, ()),
                     toolbox=None, granted=[], workspace=ws)


def test_capture_only_existing_designated_artifacts(tmp_path):
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws = _WS({"report.md": b"# Report\nresults", "src/app.py": b"print(1)"})
    output = NS(full_content="x", citations=[], confidence=0.9,
                artifacts=["report.md", "src/app.py", "missing.txt"])
    ctx = VrakshaContext.new("s")

    refs = asyncio.run(handler._capture_artifacts(output, _env(tmp_path, ws), ctx))
    assert sorted(r["name"] for r in refs) == ["app.py", "report.md"]   # missing skipped; path flattened
    rid = next(r["id"] for r in refs if r["name"] == "report.md")
    assert asyncio.run(store.get(rid)) == b"# Report\nresults"          # captured bytes are retrievable


def test_capture_noop_without_workspace_or_artifacts(tmp_path):
    handler = ExpertHandler(artifact_store=LocalArtifactStore(base_dir=tmp_path))
    ctx = VrakshaContext.new("s")
    assert asyncio.run(handler._capture_artifacts(NS(artifacts=["x"]), _env(tmp_path, None), ctx)) == []
    ws = _WS({})
    assert asyncio.run(handler._capture_artifacts(NS(artifacts=[]), _env(tmp_path, ws), ctx)) == []


# ---- Stage 2: serve (the run carries refs; the server hands back bytes) -----


def test_run_artifacts_survive_persist_and_reload(tmp_path, monkeypatch):
    # a finished run's artifact refs round-trip through SQLite (new column)
    import api.config as cfg
    import api.runs as runs_mod

    monkeypatch.setattr(cfg, "DB_PATH", str(tmp_path / "t.db"))
    store = runs_mod.RunStore()
    run = runs_mod.RunState(id="run_abc", user_id="u1", title="t", brief="b", status="delivered")
    run.report = "done"
    run.artifacts = [{"id": "run_abc/report.md", "run_id": "run_abc",
                      "name": "report.md", "mime": "text/markdown", "size": 4}]
    store.persist(run)                                   # writes the row, drops live copy

    reloaded = store.get("u1", "run_abc")
    assert reloaded is not None
    assert reloaded.artifacts == run.artifacts           # survived the DB round-trip
    assert reloaded.full_json()["artifacts"] == run.artifacts


def test_download_artifact_serves_designated_bytes_only(tmp_path, monkeypatch):
    from api.app import download_artifact
    from api.auth import User
    import api.runs as runs_mod

    # the file as it would sit in the store after capture (under the run id)
    monkeypatch.setenv("VRAKSHA_ARTIFACTS_DIR", str(tmp_path))
    ref = asyncio.run(LocalArtifactStore(base_dir=tmp_path).put("run_xyz", "report.md", b"# hi"))

    run = runs_mod.RunState(id="run_xyz", user_id="u1", title="t", brief="b")
    run.artifacts = [ref.as_dict()]
    monkeypatch.setattr(runs_mod.STORE, "get",
                        lambda uid, rid: run if (uid == "u1" and rid == "run_xyz") else None)
    user = User(id="u1", email="u@x.io", name="U", plan="free")

    resp = asyncio.run(download_artifact("run_xyz", "report.md", user))
    assert resp.body == b"# hi" and resp.media_type == "text/markdown"

    # a name the run never published is a 404, never an arbitrary disk read
    with pytest.raises(Exception) as exc:
        asyncio.run(download_artifact("run_xyz", "secrets.env", user))
    assert getattr(exc.value, "status_code", None) == 404
