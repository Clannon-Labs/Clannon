"""AST-aware code search (code.ast_search) — finds a symbol's definitions and
call-sites via a real tree-sitter parse (Python + C), not text matching. §4 of the
ratified nav-patch-tooling design (`proposals/archive/to-backend/2026-07-25_
nav-patch-tooling-design.md`), unblocked once tree-sitter landed (`f4c6e51`)."""

import asyncio

from foundation import PermissionLevel, RunResult, VrakshaContext
from registry.capabilities import discover
from registry.capabilities.handler.sandbox import DockerWorkspace
from registry.capabilities.handler.tools import ToolHandler
from registry.capabilities.schemas import ToolRequest
from tools.ast_search import AstSearchIn, AstSearchTool

discover()  # register code.ast_search alongside fs.read / fs.write / fs.patch / code.run


class _FakeWorkspace:
    """An in-memory WorkspacePort stand-in carrying raw bytes (ast_search reads
    bytes, unlike fs.read/fs.write's text-based tests/workspace_tools.py fixture)."""
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


_PY = b"def foo(x):\n    return bar(x) + 1\n\nclass Baz:\n    def method(self):\n        foo(1)\n\ndef bar(y):\n    return y\n"
_C = b"int foo(int x) {\n  return bar(x);\n}\n\nstruct Baz {\n  int a;\n};\n"
_GRANTS = frozenset({PermissionLevel.READ})


def _handler(ws) -> ToolHandler:
    return ToolHandler().scoped(allowed_keys={"code.ast_search"}, grants=_GRANTS, workspace=ws)


def test_registers_with_read_permission_and_wants_workspace():
    discover()
    from registry.capabilities import registry as reg
    spec = reg.get_tool("code.ast_search")
    assert spec is not None
    assert spec.permission == PermissionLevel.READ
    assert getattr(spec.impl, "wants_workspace", False) is True


def test_finds_definitions_and_call_sites_across_python_and_c(monkeypatch):
    ws = _FakeWorkspace({"src/main.py": _PY, "src/helper.c": _C, "README.md": b"foo bar, not code\n"})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "foo"}), ctx=VrakshaContext.new("s")))
    assert rec.success and rec.result["files_scanned"] == 2   # README.md skipped, unsupported extension
    kinds = {(m["path"], m["kind"], m["node_type"]) for m in rec.result["matches"]}
    assert ("src/main.py", "definition", "function_definition") in kinds
    assert ("src/main.py", "reference", "call") in kinds          # foo(1) inside Baz.method
    assert ("src/helper.c", "definition", "function_definition") in kinds


def test_kind_filter_narrows_to_definitions_only():
    ws = _FakeWorkspace({"a.py": _PY})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="code.ast_search", arguments={"name": "foo", "kind": "definition"}), ctx=VrakshaContext.new("s")
    ))
    assert rec.success
    assert all(m["kind"] == "definition" for m in rec.result["matches"])
    assert len(rec.result["matches"]) == 1


def test_language_filter_restricts_the_scan():
    ws = _FakeWorkspace({"a.py": _PY, "b.c": _C})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="code.ast_search", arguments={"name": "foo", "language": "c"}), ctx=VrakshaContext.new("s")
    ))
    assert rec.success and rec.result["files_scanned"] == 1
    assert all(m["path"] == "b.c" for m in rec.result["matches"])


def test_path_prefix_scopes_the_scan():
    ws = _FakeWorkspace({"src/a.py": _PY, "vendor/b.py": _PY})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="code.ast_search", arguments={"name": "foo", "path_prefix": "src/"}), ctx=VrakshaContext.new("s")
    ))
    assert rec.success and rec.result["files_scanned"] == 1
    assert all(m["path"].startswith("src/") for m in rec.result["matches"])


def test_c_pointer_return_declarator_is_unwrapped_to_the_plain_name():
    # int *foo(int x) -- the name sits behind a pointer_declarator wrapper; proves
    # _c_declarator_name actually walks through it rather than only handling the
    # simple case
    src = b"int *foo(int x) {\n  return 0;\n}\n"
    ws = _FakeWorkspace({"a.c": src})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "foo"}), ctx=VrakshaContext.new("s")))
    assert rec.success and len(rec.result["matches"]) == 1
    assert rec.result["matches"][0]["kind"] == "definition"


def test_struct_union_enum_all_match_by_name():
    src = b"struct Point { int x; };\nunion U { int a; };\nenum Color { RED };\n"
    ws = _FakeWorkspace({"a.c": src})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "Point"}), ctx=VrakshaContext.new("s")))
    assert rec.success and len(rec.result["matches"]) == 1
    assert rec.result["matches"][0]["node_type"] == "struct_specifier"


def test_attribute_calls_are_not_matched_v1_scope():
    # obj.foo(x) -- the callee is an `attribute` node, not a bare identifier; the
    # tool's own description says this is out of v1 scope, proven here so a future
    # change either keeps this honest or updates the description alongside it
    src = b"def run():\n    obj.foo(1)\n"
    ws = _FakeWorkspace({"a.py": src})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "foo"}), ctx=VrakshaContext.new("s")))
    assert rec.success and rec.result["matches"] == []


def test_no_match_is_a_clean_empty_result_not_an_error():
    ws = _FakeWorkspace({"a.py": _PY})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "nope"}), ctx=VrakshaContext.new("s")))
    assert rec.success and rec.result["matches"] == [] and rec.result["files_scanned"] == 1


def test_unreadable_file_does_not_sink_the_whole_search():
    class _Flaky(_FakeWorkspace):
        async def read_bytes(self, rel_path):
            if rel_path == "bad.py":
                raise OSError("disk fault")
            return await super().read_bytes(rel_path)
    ws = _Flaky({"bad.py": _PY, "good.py": _PY})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "foo"}), ctx=VrakshaContext.new("s")))
    assert rec.success and rec.result["files_scanned"] == 1
    assert all(m["path"] == "good.py" for m in rec.result["matches"])
    # honest, not silent: the skipped file is counted and the result is flagged
    # non-exhaustive, not presented as if it were the complete picture
    assert rec.result["files_skipped"] == 1 and rec.result["truncated"] is True


def test_oversized_file_is_skipped_and_flagged_not_silently_dropped(monkeypatch):
    import tools.ast_search as mod
    monkeypatch.setattr(mod, "_MAX_FILE_BYTES", 10)   # smaller than _PY
    ws = _FakeWorkspace({"big.py": _PY})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "foo"}), ctx=VrakshaContext.new("s")))
    assert rec.success and rec.result["files_scanned"] == 0
    assert rec.result["files_skipped"] == 1 and rec.result["truncated"] is True


def test_kind_filter_applies_during_the_walk_not_after_the_match_cap(monkeypatch):
    # the bug this guards: filtering matches AFTER _walk collects up to
    # _MAX_MATCHES unfiltered hits means a file with >= _MAX_MATCHES call-sites
    # of `name`, followed later by its ONE definition, would silently report
    # "no definition" once every collected hit turned out to be a reference and
    # got filtered away -- kind must narrow what _walk itself collects
    import tools.ast_search as mod
    monkeypatch.setattr(mod, "_MAX_MATCHES", 3)
    src = b"".join(b"foo(%d)\n" % i for i in range(5)) + b"def foo(x):\n    return x\n"
    ws = _FakeWorkspace({"a.py": src})
    h = _handler(ws)
    rec = asyncio.run(h.call_tool(
        ToolRequest(key="code.ast_search", arguments={"name": "foo", "kind": "definition"}), ctx=VrakshaContext.new("s")
    ))
    assert rec.success
    assert len(rec.result["matches"]) == 1
    assert rec.result["matches"][0]["kind"] == "definition"


def test_workspace_tool_without_workspace_fails():
    h = ToolHandler().scoped(allowed_keys={"code.ast_search"}, grants=_GRANTS, workspace=None)
    rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "foo"}), ctx=VrakshaContext.new("s")))
    assert not rec.success and "workspace" in (rec.error or "")


def test_runs_against_the_real_docker_workspace_no_docker_needed():
    # file I/O needs no container, same proof shape as workspace_tools.py's fs.*
    # tests -- confirms the tool works through the REAL WorkspacePort, not just
    # the in-memory stand-in above
    ws = DockerWorkspace()
    try:
        asyncio.run(ws.write_bytes("a.py", _PY))
        h = _handler(ws)
        rec = asyncio.run(h.call_tool(ToolRequest(key="code.ast_search", arguments={"name": "bar"}), ctx=VrakshaContext.new("s")))
        assert rec.success and len(rec.result["matches"]) == 2   # one definition, one call-site
    finally:
        asyncio.run(ws.close())
