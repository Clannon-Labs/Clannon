"""
Tests for the text diff tool (text.diff).

Acceptance matrix:
  (a) tool is discoverable through the registry with populated metadata, READ perm
  (b) run() on valid inputs returns a correct unified/context/ndiff render with
      accurate added/removed counts, deterministically
  (c) edge cases (identical, empty, trailing-newline-only, oversized) return a
      structured safe result, never raise
  (d) the tool touches no network / filesystem / subprocess primitive
"""

import asyncio

from tools.diff import DiffIn, DiffOut, DiffTool


def _run(coro):
    return asyncio.run(coro)


# ─── (a) registry discovery ────────────────────────────────────────────────

def test_diff_tool_registered():
    from registry.capabilities import discover, registry
    discover()
    spec = registry.get_tool("text.diff")
    assert spec is not None, "text.diff not found in registry after discover()"


def test_diff_tool_not_broken():
    from registry.capabilities import discover, registry
    discover()
    assert "text.diff" not in {b.key for b in registry.broken()}


def test_diff_tool_metadata_populated():
    from registry.capabilities import discover, registry
    discover()
    spec = registry.get_tool("text.diff")
    assert spec.description
    assert spec.input_schema is not None
    assert spec.output_schema is not None


def test_diff_tool_permission_read():
    from foundation import PermissionLevel
    from registry.capabilities import discover, registry
    discover()
    spec = registry.get_tool("text.diff")
    assert spec.permission == PermissionLevel.READ


# ─── (b) valid inputs produce a correct diff + counts ──────────────────────

def test_unified_diff_basic():
    result = _run(DiffTool().run(DiffIn(
        a="line1\nline2\nline3",
        b="line1\nCHANGED\nline3",
        a_label="old.txt",
        b_label="new.txt",
    )))
    assert isinstance(result, DiffOut)
    assert result.error == ""
    assert result.changed is True
    assert result.content_type == "text/x-diff"
    assert "--- old.txt" in result.diff
    assert "+++ new.txt" in result.diff
    assert "-line2" in result.diff
    assert "+CHANGED" in result.diff
    assert result.added == 1 and result.removed == 1     # one line replaced


def test_pure_addition_counts():
    result = _run(DiffTool().run(DiffIn(a="a\nb", b="a\nb\nc\nd")))
    assert result.changed is True
    assert result.added == 2 and result.removed == 0


def test_pure_deletion_counts():
    result = _run(DiffTool().run(DiffIn(a="a\nb\nc\nd", b="a\nd")))
    assert result.changed is True
    assert result.added == 0 and result.removed == 2


def test_context_format():
    result = _run(DiffTool().run(DiffIn(
        a="x\ny\nz", b="x\nY\nz", format="context", a_label="L", b_label="R",
    )))
    assert result.error == "" and result.changed is True
    assert "*** L" in result.diff and "--- R" in result.diff
    assert result.added == 1 and result.removed == 1


def test_ndiff_format():
    result = _run(DiffTool().run(DiffIn(a="alpha\nbeta", b="alpha\ngamma", format="ndiff")))
    assert result.error == "" and result.changed is True
    assert "- beta" in result.diff
    assert "+ gamma" in result.diff


def test_counts_are_format_independent():
    a, b = "one\ntwo\nthree", "one\nTWO\nthree\nfour"
    counts = set()
    for fmt in ("unified", "context", "ndiff"):
        r = _run(DiffTool().run(DiffIn(a=a, b=b, format=fmt)))
        counts.add((r.added, r.removed))
    assert counts == {(2, 1)}, "added/removed must be independent of render format"


def test_output_is_deterministic():
    args = DiffIn(a="p\nq\nr", b="p\nQ\nr\ns")
    r1 = _run(DiffTool().run(args))
    r2 = _run(DiffTool().run(args))
    assert r1.diff == r2.diff and (r1.added, r1.removed) == (r2.added, r2.removed)


# ─── (c) edge cases: safe result, never raise ──────────────────────────────

def test_identical_inputs_report_unchanged():
    result = _run(DiffTool().run(DiffIn(a="same\ntext", b="same\ntext")))
    assert result.changed is False
    assert result.diff == ""
    assert result.added == 0 and result.removed == 0
    assert result.error == ""


def test_trailing_newline_only_is_line_identical():
    result = _run(DiffTool().run(DiffIn(a="abc", b="abc\n")))
    assert result.changed is False and result.diff == ""


def test_both_empty():
    result = _run(DiffTool().run(DiffIn(a="", b="")))
    assert result.changed is False and result.error == ""


def test_empty_to_content_is_all_added():
    result = _run(DiffTool().run(DiffIn(a="", b="new1\nnew2")))
    assert result.changed is True
    assert result.added == 2 and result.removed == 0


def test_oversized_input_fails_closed():
    big = "x\n" * 100_001            # ~200,002 chars per side → over the combined cap
    result = _run(DiffTool().run(DiffIn(a=big, b=big + "y")))
    assert result.error == "inputs_too_large"
    assert result.diff == "" and result.changed is False


# ─── (d) purity: no external calls ─────────────────────────────────────────

def test_no_network_filesystem_subprocess(monkeypatch):
    import socket
    import subprocess
    import urllib.request

    calls: list[str] = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: calls.append("socket") or [])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append("subprocess"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: calls.append("urllib"))

    _run(DiffTool().run(DiffIn(a="a\nb", b="a\nc")))
    assert calls == [], f"run() made unexpected external calls: {calls}"
