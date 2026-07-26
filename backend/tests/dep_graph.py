"""Dependency-graph traversal (code.dep_graph) — BFS over import/include edges via a
real tree-sitter parse (Python + C), from a starting file outward. §5 of the ratified
nav-patch-tooling design (`proposals/archive/to-backend/2026-07-25_nav-patch-tooling-
design.md`), built on §4's landed code.ast_search."""

import asyncio

from foundation import PermissionLevel, RunResult, VrakshaContext
from registry.capabilities import discover
from registry.capabilities.handler.tools import ToolHandler
from registry.capabilities.schemas import ToolRequest

discover()  # register code.dep_graph alongside fs.read / fs.write / fs.patch / code.run / code.ast_search


class _FakeWorkspace:
    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)
    async def write(self, rel_path, content): self.files[rel_path] = content.encode()
    async def write_bytes(self, rel_path, data): self.files[rel_path] = data
    async def read(self, rel_path): return self.files[rel_path].decode()
    async def read_bytes(self, rel_path): return self.files[rel_path]
    async def list(self): return sorted(self.files)
    async def run(self, command, *, timeout_s=None): return RunResult(0, command, "", False)
    async def reset(self): self.files.clear()
    async def close(self): pass


_GRANTS = frozenset({PermissionLevel.READ})


def _handler(ws) -> ToolHandler:
    return ToolHandler().scoped(allowed_keys={"code.dep_graph"}, grants=_GRANTS, workspace=ws)


def _call(ws, **args):
    h = _handler(ws)
    return asyncio.run(h.call_tool(ToolRequest(key="code.dep_graph", arguments=args), ctx=VrakshaContext.new("s")))


def test_registers_with_read_permission_and_wants_workspace():
    discover()
    from registry.capabilities import registry as reg
    spec = reg.get_tool("code.dep_graph")
    assert spec is not None
    assert spec.permission == PermissionLevel.READ
    assert getattr(spec.impl, "wants_workspace", False) is True


def test_python_absolute_import_resolves_and_traverses():
    ws = _FakeWorkspace({
        "main.py": b"import pkg.mod\n",
        "pkg/__init__.py": b"",
        "pkg/mod.py": b"x = 1\n",
    })
    rec = _call(ws, start_path="main.py")
    assert rec.success
    paths = {n["path"] for n in rec.result["nodes"]}
    assert paths == {"main.py", "pkg/mod.py"}
    edge = rec.result["edges"][0]
    assert edge["source"] == "main.py" and edge["target"] == "pkg/mod.py" and edge["resolved"] is True


def test_python_from_import_resolves_module_not_the_imported_name():
    ws = _FakeWorkspace({"main.py": b"from pkg.mod import thing\n", "pkg/mod.py": b"thing = 1\n"})
    rec = _call(ws, start_path="main.py")
    assert rec.success and len(rec.result["edges"]) == 1
    assert rec.result["edges"][0]["target"] == "pkg/mod.py"


def test_python_relative_import_resolves_against_importing_files_directory():
    ws = _FakeWorkspace({
        "pkg/__init__.py": b"",
        "pkg/main.py": b"from . import sibling\nfrom .sibling import thing\n",
        "pkg/sibling.py": b"thing = 1\n",
    })
    rec = _call(ws, start_path="pkg/main.py")
    assert rec.success
    targets = {e["target"] for e in rec.result["edges"]}
    assert "pkg/sibling.py" in targets or "pkg/__init__.py" in targets  # `from . import sibling` -> package init
    assert "pkg/sibling.py" in targets  # `from .sibling import thing` -> the sibling module itself


def test_c_quoted_include_resolves_relative_to_including_file():
    ws = _FakeWorkspace({
        "src/main.c": b'#include "../inc/foo.h"\n',
        "inc/foo.h": b"int foo(void);\n",
    })
    rec = _call(ws, start_path="src/main.c")
    assert rec.success and len(rec.result["nodes"]) == 2
    assert any(n["path"] == "inc/foo.h" for n in rec.result["nodes"])


def test_c_system_include_is_unresolved_not_dropped():
    ws = _FakeWorkspace({"main.c": b"#include <stdio.h>\nint main(void){return 0;}\n"})
    rec = _call(ws, start_path="main.c")
    assert rec.success and len(rec.result["nodes"]) == 1  # nothing to traverse into
    assert len(rec.result["edges"]) == 1
    edge = rec.result["edges"][0]
    assert edge["resolved"] is False and edge["target"] == "" and edge["raw"] == "stdio.h"


def test_unresolved_python_import_is_surfaced_not_silently_dropped():
    ws = _FakeWorkspace({"main.py": b"import nope_not_here\n"})
    rec = _call(ws, start_path="main.py")
    assert rec.success and len(rec.result["nodes"]) == 1
    assert rec.result["edges"][0]["resolved"] is False and rec.result["edges"][0]["raw"] == "nope_not_here"


def test_dependents_direction_finds_incoming_importers():
    ws = _FakeWorkspace({
        "lib.py": b"x = 1\n",
        "a.py": b"import lib\n",
        "b.py": b"import lib\n",
        "unrelated.py": b"import os\n",
    })
    rec = _call(ws, start_path="lib.py", direction="dependents")
    assert rec.success
    paths = {n["path"] for n in rec.result["nodes"]}
    assert paths == {"lib.py", "a.py", "b.py"}


def test_both_direction_combines_incoming_and_outgoing():
    ws = _FakeWorkspace({
        "root.py": b"import mid\n",
        "mid.py": b"import leaf\n",
        "leaf.py": b"x = 1\n",
    })
    rec = _call(ws, start_path="mid.py", direction="both", max_depth=1)
    assert rec.success
    paths = {n["path"] for n in rec.result["nodes"]}
    assert paths == {"root.py", "mid.py", "leaf.py"}


def test_max_depth_bounds_the_traversal():
    ws = _FakeWorkspace({
        "a.py": b"import b\n",
        "b.py": b"import c\n",
        "c.py": b"x = 1\n",
    })
    rec = _call(ws, start_path="a.py", max_depth=1)
    assert rec.success
    paths = {n["path"] for n in rec.result["nodes"]}
    assert paths == {"a.py", "b.py"}   # c.py is two hops away, past max_depth=1


def test_cycle_does_not_infinite_loop():
    ws = _FakeWorkspace({"a.py": b"import b\n", "b.py": b"import a\n"})
    rec = _call(ws, start_path="a.py", max_depth=5)
    assert rec.success
    paths = {n["path"] for n in rec.result["nodes"]}
    assert paths == {"a.py", "b.py"}   # visited-set guards the cycle, no runaway


def test_path_prefix_scopes_the_underlying_scan():
    ws = _FakeWorkspace({"src/a.py": b"from .lib import x\n", "src/lib.py": b"x = 1\n", "vendor/lib.py": b"y = 2\n"})
    rec = _call(ws, start_path="src/a.py", path_prefix="src/")
    assert rec.success
    paths = {n["path"] for n in rec.result["nodes"]}
    assert paths == {"src/a.py", "src/lib.py"}


def test_start_path_not_in_workspace_is_a_structured_error():
    ws = _FakeWorkspace({"a.py": b"x = 1\n"})
    rec = _call(ws, start_path="missing.py")
    assert rec.success and rec.result["ok"] is False
    assert "not found" in rec.result["error"]


def test_invalid_direction_is_rejected():
    ws = _FakeWorkspace({"a.py": b"x = 1\n"})
    rec = _call(ws, start_path="a.py", direction="sideways")
    assert not rec.success


def test_unreadable_file_does_not_sink_the_whole_traversal():
    class _Flaky(_FakeWorkspace):
        async def read_bytes(self, rel_path):
            if rel_path == "bad.py":
                raise OSError("disk fault")
            return await super().read_bytes(rel_path)
    ws = _Flaky({"a.py": b"import bad\n", "bad.py": b"import os\n"})
    rec = _call(ws, start_path="a.py")
    assert rec.success
    # `bad.py` itself failed to parse, so its own edges are missing, but the edge
    # POINTING at it (from a.py) still resolved and is not silently dropped
    assert any(n["path"] == "bad.py" for n in rec.result["nodes"])
    assert rec.result["files_skipped"] == 1 and rec.result["truncated"] is True


def test_workspace_tool_without_workspace_fails():
    h = ToolHandler().scoped(allowed_keys={"code.dep_graph"}, grants=_GRANTS, workspace=None)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.dep_graph", arguments={"start_path": "a.py"}), ctx=VrakshaContext.new("s")))
    assert not rec.success and "workspace" in (rec.error or "")
