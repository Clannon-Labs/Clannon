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
