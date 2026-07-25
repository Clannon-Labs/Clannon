"""The ToolHandler injects the per-run workspace into `wants_workspace` tools, and
refuses to run one outside a workspace scope."""

import asyncio

from foundation import PermissionLevel, RunResult, VrakshaContext
from registry.capabilities import discover
from registry.capabilities.handler.tools import ToolHandler
from registry.capabilities.schemas import ToolRequest

discover()  # register fs.read / fs.write / fs.patch / code.run


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


# ─── fs.read's line-range extension (the truncation fix) ───────────────────

def _handler(ws) -> ToolHandler:
    return ToolHandler().scoped(allowed_keys={"fs.write", "fs.read", "fs.patch"}, grants=_GRANTS, workspace=ws)


def test_fs_read_whole_file_still_truncates_unchanged():
    ws = _FakeWorkspace()
    ws.files["big.txt"] = "x" * 50_000
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="fs.read", arguments={"path": "big.txt"}), ctx=VrakshaContext.new("s")))
    assert rec.success and rec.result["truncated"] is True
    assert len(rec.result["content"]) == 40_000


def test_fs_read_range_reaches_content_past_the_truncation_point():
    """The correctness fix: a whole-file read of a big file never sees past 40k
    chars, but a ranged read can target any line directly -- proves the gap
    fs.patch is meant to close is actually closed."""
    ws = _FakeWorkspace()
    lines = [f"line {i}" for i in range(1, 20_001)]  # far more than 40k chars total
    ws.files["big.txt"] = "\n".join(lines)
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.read", arguments={"path": "big.txt", "start_line": 19_999, "end_line": 20_000}), ctx,
    ))
    assert rec.success and rec.result["truncated"] is False
    assert "line 19999" in rec.result["content"]
    assert "line 20000" in rec.result["content"]
    # cat -n style: the line number is present in the returned text
    assert "19999" in rec.result["content"].splitlines()[0]


def test_fs_read_range_past_end_of_file_fails_closed():
    ws = _FakeWorkspace()
    ws.files["small.txt"] = "one\ntwo\nthree"
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.read", arguments={"path": "small.txt", "start_line": 10, "end_line": 12}),
        ctx=VrakshaContext.new("s"),
    ))
    # the tool call itself succeeds (no exception) -- the failure is in its own
    # structured output, same convention as fs.write/fs.read's confinement errors
    assert rec.success and rec.result["ok"] is False and "past end of file" in rec.result["error"]


def test_fs_read_range_requires_both_bounds_together():
    ws = _FakeWorkspace()
    ws.files["small.txt"] = "one\ntwo"
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.read", arguments={"path": "small.txt", "start_line": 1}),
        ctx=VrakshaContext.new("s"),
    ))
    assert not rec.success and "bad arguments" in (rec.error or "")


# ─── fs.patch: replace / insert / delete, all line-range operations ─────────

def test_fs_patch_replaces_a_line_range():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo\nthree\nfour\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 2, "end_line": 3, "replacement": "TWO\nTHREE"}), ctx,
    ))
    assert rec.success and rec.result["ok"] is True
    assert ws.files["a.py"] == "one\nTWO\nTHREE\nfour\n"


def test_fs_patch_inserts_before_a_line_without_replacing_anything():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 2, "end_line": 1, "replacement": "ONE-AND-A-HALF"}), ctx,
    ))
    assert rec.success and rec.result["ok"] is True
    assert ws.files["a.py"] == "one\nONE-AND-A-HALF\ntwo\n"


def test_fs_patch_inserts_at_end_of_file():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 3, "end_line": 2, "replacement": "three"}), ctx,
    ))
    assert rec.success and rec.result["ok"] is True
    assert ws.files["a.py"] == "one\ntwo\nthree\n"


def test_fs_patch_deletes_a_line_range_with_empty_replacement():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo\nthree\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 2, "end_line": 2, "replacement": ""}), ctx,
    ))
    assert rec.success and rec.result["ok"] is True
    assert ws.files["a.py"] == "one\nthree\n"


def test_fs_patch_out_of_bounds_range_fails_closed_without_writing():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 5, "end_line": 6, "replacement": "x"}), ctx,
    ))
    assert rec.success and rec.result["ok"] is False
    assert ws.files["a.py"] == "one\ntwo\n"          # untouched on failure


def test_fs_patch_rejects_end_line_more_than_one_below_start_line():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 5, "end_line": 1, "replacement": "x"}), ctx,
    ))
    assert not rec.success and "bad arguments" in (rec.error or "")


def test_fs_patch_preserves_a_missing_trailing_newline():
    ws = _FakeWorkspace()
    ws.files["a.py"] = "one\ntwo"    # no trailing newline
    h = _handler(ws)
    ctx = VrakshaContext.new("s")
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="fs.patch", arguments={"path": "a.py", "start_line": 2, "end_line": 2, "replacement": "TWO"}), ctx,
    ))
    assert rec.success
    assert ws.files["a.py"] == "one\nTWO"


# ─── the fix, proven end-to-end: read a slice, patch it, without ever seeing
# or rewriting the whole (over-cap) file ─────────────────────────────────────

def test_read_range_then_patch_edits_a_file_bigger_than_the_whole_file_cap():
    ws = _FakeWorkspace()
    lines = [f"line {i}" for i in range(1, 15_000)]
    ws.files["huge.py"] = "\n".join(lines) + "\n"
    h = _handler(ws)
    ctx = VrakshaContext.new("s")

    async def body():
        read = await h.call_tool(
            ToolRequest(key="fs.read", arguments={"path": "huge.py", "start_line": 14_000, "end_line": 14_000}), ctx,
        )
        assert read.success and "line 14000" in read.result["content"]
        patch = await h.call_tool(
            ToolRequest(key="fs.patch", arguments={
                "path": "huge.py", "start_line": 14_000, "end_line": 14_000, "replacement": "PATCHED",
            }), ctx,
        )
        assert patch.success and patch.result["ok"] is True

    asyncio.run(body())
    result_lines = ws.files["huge.py"].splitlines()
    assert result_lines[13_999] == "PATCHED"
    assert result_lines[0] == "line 1"                 # everything else survived intact
    assert len(result_lines) == len(lines)              # no silent truncation of the tail
