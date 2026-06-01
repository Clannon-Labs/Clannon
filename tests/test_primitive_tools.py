"""Tests for live primitive tools exposed through the registry."""

from pathlib import Path

from get_root import root
from registry.discovery import discover_registry_modules
from registry.register import Registry


def test_filesystem_primitive_operates_inside_workspace():
    """Filesystem primitive can write, read, search, and stat workspace files."""
    discover_registry_modules()
    entry = Registry.get("tool.filesystem.operate")
    assert entry is not None

    tool = entry.cls()
    test_path = Path(".primitive_tool_test.txt")
    absolute_path = root.project / test_path

    try:
        write_result = tool.call({
            "operation": "write",
            "path": test_path.as_posix(),
            "content": "alpha\nbeta\n",
        })
        assert write_result["success"] is True

        read_result = tool.call({
            "operation": "read",
            "path": test_path.as_posix(),
        })
        assert read_result["success"] is True
        assert read_result["data"]["content"] == "alpha\nbeta\n"

        search_result = tool.call({
            "operation": "search",
            "path": test_path.as_posix(),
            "query": "beta",
        })
        assert search_result["success"] is True
        assert search_result["data"]["matches"][0]["line"] == 2

        stat_result = tool.call({
            "operation": "stat",
            "path": test_path.as_posix(),
        })
        assert stat_result["success"] is True
        assert stat_result["data"]["exists"] is True

    finally:
        if absolute_path.exists():
            absolute_path.unlink()


def test_filesystem_primitive_blocks_project_escape():
    """Filesystem primitive refuses paths outside the project root."""
    discover_registry_modules()
    entry = Registry.get("tool.filesystem.operate")
    assert entry is not None

    result = entry.cls().call({
        "operation": "read",
        "path": "../outside.txt",
    })

    assert result["success"] is False
    assert "outside project root" in result["error"]


def test_new_primitive_tool_set_registers_with_safe_first_behavior():
    """Each primitive directory has one registered tool with safe behavior."""
    discover_registry_modules()

    expected_keys = {
        "tool.agent.invoke",
        "tool.filesystem.operate",
        "tool.llm.generate",
        "tool.mcp.call",
        "tool.shell.run",
        "tool.system.inspect",
        "tool.web.fetch",
    }
    assert expected_keys.issubset(Registry.all())

    system_result = Registry.get("tool.system.inspect").cls().call({
        "include_python": False,
    })
    assert system_result["success"] is True
    assert "project_root" in system_result["data"]

    assert Registry.get("tool.agent.invoke").cls().call({
        "expert": "expert.review.review",
        "payload": {},
        "reason": "test",
    })["success"] is False

    assert Registry.get("tool.llm.generate").cls().call({
        "prompt": "hello",
        "purpose": "test",
    })["success"] is False

    assert Registry.get("tool.mcp.call").cls().call({
        "capability": "external.demo",
        "arguments": {},
        "reason": "test",
    })["success"] is False

    assert Registry.get("tool.shell.run").cls().call({
        "command": "git status",
    })["success"] is False

    assert Registry.get("tool.web.fetch").cls().call({
        "url": "https://example.com",
    })["success"] is False
