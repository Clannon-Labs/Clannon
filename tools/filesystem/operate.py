"""Workspace-scoped filesystem primitive.

This is intentionally one composable primitive instead of many narrow file
tools. It keeps deterministic filesystem operations behind a single schema and
relies on project-root resolution plus immutable-file checks for first-line
safety.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from registry import tool
from resolve.resolve_within_project import PROJECT_ROOT, resolve_path
from src.utils.get_tree import get_tree
from src.utils.immutables import is_immutable
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@tool(enabled=True, domain="filesystem", tags=["primitive", "workspace"])
class FilesystemOperateTool:
    """Perform bounded filesystem operations inside the project workspace."""

    name = "operate"
    description = (
        "Perform a workspace-scoped filesystem operation: read, write, append, "
        "list, search, exists, or stat."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write", "append", "list", "search", "exists", "stat"],
                "description": "Filesystem operation to perform.",
            },
            "path": {
                "type": "string",
                "description": "Path inside the project workspace.",
            },
            "content": {
                "type": "string",
                "description": "Content for write or append operations.",
                "default": "",
            },
            "query": {
                "type": "string",
                "description": "Text to search for during search operations.",
                "default": "",
            },
            "max_bytes": {
                "type": "integer",
                "description": "Maximum bytes to read from a file.",
                "default": 60000,
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum directory depth for list operations.",
                "default": 3,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum search matches to return.",
                "default": 50,
            },
            "create_parents": {
                "type": "boolean",
                "description": "Create missing parent directories for write or append.",
                "default": False,
            },
        },
        "required": ["operation", "path"],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Dispatch a validated operation to the corresponding helper."""
        operation = str(tool_input.get("operation", "")).strip().lower()
        path = str(tool_input.get("path", "")).strip()

        if not operation:
            return _fail("operation is required")
        if not path:
            return _fail("path is required")

        resolved = resolve_path(path)
        if not resolved.success:
            return _fail(resolved.error or "path is not allowed")

        target = resolved.result

        try:
            if operation == "read":
                return _read(target, _positive_int(tool_input.get("max_bytes"), 60000))
            if operation == "write":
                return _write(
                    target,
                    str(tool_input.get("content", "")),
                    append=False,
                    create_parents=bool(tool_input.get("create_parents", False)),
                )
            if operation == "append":
                return _write(
                    target,
                    str(tool_input.get("content", "")),
                    append=True,
                    create_parents=bool(tool_input.get("create_parents", False)),
                )
            if operation == "list":
                return _list(target, _positive_int(tool_input.get("max_depth"), 3))
            if operation == "search":
                return _search(
                    target,
                    str(tool_input.get("query", "")),
                    _positive_int(tool_input.get("max_results"), 50),
                )
            if operation == "exists":
                return _ok({"path": _relative(target), "exists": target.exists()})
            if operation == "stat":
                return _stat(target)

            return _fail(f"unsupported operation: {operation}")

        except UnicodeDecodeError:
            return _fail(f"{_relative(target)} is not valid UTF-8 text")
        except OSError as exc:
            return _fail(str(exc))


def _read(target: Path, max_bytes: int) -> Dict[str, Any]:
    """Read a UTF-8 file with a byte cap and truncation flag."""
    if not target.exists():
        return _fail(f"{_relative(target)} does not exist")
    if target.is_dir():
        return _fail(f"{_relative(target)} is a directory; use list")

    raw = target.read_bytes()
    truncated = len(raw) > max_bytes
    content = raw[:max_bytes].decode("utf-8")

    return _ok({
        "path": _relative(target),
        "content": content,
        "bytes": min(len(raw), max_bytes),
        "truncated": truncated,
    })


def _write(
    target: Path,
    content: str,
    *,
    append: bool,
    create_parents: bool,
) -> Dict[str, Any]:
    """Write or append text while respecting immutable-file protection."""
    if is_immutable(target):
        return _fail(f"{_relative(target)} is immutable")
    if target.exists() and target.is_dir():
        return _fail(f"{_relative(target)} is a directory")
    if not target.parent.exists():
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            return _fail(f"parent directory does not exist: {_relative(target.parent)}")

    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as file:
        file.write(content)

    return _ok({
        "path": _relative(target),
        "operation": "append" if append else "write",
        "bytes": len(content.encode("utf-8")),
    })


def _list(target: Path, max_depth: int) -> Dict[str, Any]:
    """Render a directory tree or single-file listing for the target path."""
    if not target.exists():
        return _fail(f"{_relative(target)} does not exist")

    return _ok({
        "path": _relative(target),
        "tree": get_tree(target, max_depth=max_depth),
    })


def _search(target: Path, query: str, max_results: int) -> Dict[str, Any]:
    """Search UTF-8 text files under a path using simple case-insensitive match."""
    query = query.strip()
    if not query:
        return _fail("query is required for search")
    if not target.exists():
        return _fail(f"{_relative(target)} does not exist")

    files = [target] if target.is_file() else _iter_text_files(target)
    matches: list[dict[str, Any]] = []

    for file_path in files:
        try:
            for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
                if query.lower() in line.lower():
                    matches.append({
                        "path": _relative(file_path),
                        "line": line_number,
                        "text": line[:300],
                    })
                    if len(matches) >= max_results:
                        return _ok({"query": query, "matches": matches, "truncated": True})
        except (UnicodeDecodeError, OSError):
            continue

    return _ok({"query": query, "matches": matches, "truncated": False})


def _stat(target: Path) -> Dict[str, Any]:
    """Return existence/type/size metadata for a path."""
    if not target.exists():
        return _ok({"path": _relative(target), "exists": False})

    stat = target.stat()
    return _ok({
        "path": _relative(target),
        "exists": True,
        "is_file": target.is_file(),
        "is_dir": target.is_dir(),
        "bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    })


def _iter_text_files(root_path: Path) -> list[Path]:
    """Return candidate files for search while skipping noisy dependency/cache dirs."""
    ignored = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
    return [
        path
        for path in root_path.rglob("*")
        if path.is_file()
        and not any(part in ignored for part in path.relative_to(PROJECT_ROOT).parts)
    ]


def _relative(path: Path) -> str:
    """Format a path relative to the project root when possible."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _positive_int(value: Any, default: int) -> int:
    """Parse a positive integer with a safe default fallback."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _ok(data: dict[str, Any]) -> Dict[str, Any]:
    """Build the standard successful tool envelope."""
    return {"success": True, "data": data, "error": None}


def _fail(error: str) -> Dict[str, Any]:
    """Build the standard failed tool envelope."""
    return {"success": False, "data": None, "error": error}
