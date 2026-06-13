"""DockerWorkspace: path confinement, execution gating, and lifecycle.

These checks need no Docker (file I/O is a private temp dir; run() short-circuits
when the sandbox is disabled). The real container exec is covered by the manual
smoke, since CI may not have a Docker daemon.
"""

import asyncio

import pytest

from foundation import RunResult, WorkspacePort
from registry.capabilities.handler.sandbox import DockerWorkspace


def _run(coro):
    return asyncio.run(coro)


def test_satisfies_workspace_port():
    ws = DockerWorkspace()
    try:
        assert isinstance(ws, WorkspacePort)
    finally:
        _run(ws.close())


def test_file_io_confined():
    async def body():
        ws = DockerWorkspace()
        try:
            await ws.write("a.txt", "hello")
            await ws.write("sub/b.txt", "world")
            assert await ws.read("a.txt") == "hello"
            assert await ws.list() == ["a.txt", "sub/b.txt"]
        finally:
            await ws.close()
    _run(body())


@pytest.mark.parametrize("bad", ["../escape", "/etc/passwd", "a/../../x", "", "x\x00y"])
def test_path_escape_rejected(bad):
    async def body():
        ws = DockerWorkspace()
        try:
            with pytest.raises(ValueError):
                await ws.write(bad, "x")
        finally:
            await ws.close()
    _run(body())


def test_run_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VRAKSHA_ENABLE_SANDBOX", raising=False)

    async def body():
        ws = DockerWorkspace()
        try:
            r = await ws.run("echo hi")          # no Docker touched when disabled
            assert isinstance(r, RunResult)
            assert not r.ok and "disabled" in r.stderr
        finally:
            await ws.close()
    _run(body())


def test_close_idempotent_and_removes_dir():
    ws = DockerWorkspace()
    root = ws._root
    assert root.exists()
    _run(ws.close())
    _run(ws.close())                              # idempotent
    assert not root.exists()
