"""The ToolHandler injects the per-run workspace into `wants_workspace` tools, and
refuses to run one outside a workspace scope."""

import asyncio

from foundation import PermissionLevel, RunResult, VrakshaContext
from registry.capabilities import discover
from registry.capabilities.handler.tools import ToolHandler
from registry.capabilities.schemas import ToolRequest

discover()  # register fs.read / fs.write / code.run


class _FakeWorkspace:
    """An in-memory WorkspacePort stand-in (no Docker)."""
    def __init__(self):
        self.files: dict[str, str] = {}
    async def write(self, rel_path, content): self.files[rel_path] = content
    async def read(self, rel_path): return self.files[rel_path]
    async def list(self): return sorted(self.files)
    async def run(self, command, *, timeout_s=None): return RunResult(0, command, "", False)
    async def reset(self): self.files.clear()
    async def close(self): pass


_GRANTS = frozenset({PermissionLevel.READ, PermissionLevel.WRITE, PermissionLevel.EXECUTE})


def test_workspace_tools_get_the_injected_workspace():
    ws = _FakeWorkspace()
    h = ToolHandler().scoped(allowed_keys={"fs.write", "fs.read", "code.run"}, grants=_GRANTS, workspace=ws)
    ctx = VrakshaContext.new("s")

    async def body():
        w = await h.call_tool(ToolRequest(key="fs.write", arguments={"path": "a.txt", "content": "hi"}), ctx)
        assert w.success and ws.files["a.txt"] == "hi"
        r = await h.call_tool(ToolRequest(key="fs.read", arguments={"path": "a.txt"}), ctx)
        assert r.success and r.result["content"] == "hi"
        c = await h.call_tool(ToolRequest(key="code.run", arguments={"command": "echo hi"}), ctx)
        assert c.success and c.result["exit_code"] == 0
    asyncio.run(body())


def test_workspace_tool_without_workspace_fails():
    h = ToolHandler().scoped(allowed_keys={"fs.write"}, grants=_GRANTS, workspace=None)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(ToolRequest(key="fs.write", arguments={"path": "a.txt", "content": "x"}), ctx))
    assert not rec.success and "workspace" in (rec.error or "")
