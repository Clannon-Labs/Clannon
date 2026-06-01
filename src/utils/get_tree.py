"""Directory tree rendering for the read_file tool.

When `read_file` is given a directory, it returns this tree representation
instead of file content.
"""

from pathlib import Path

# Directories we never descend into: noisy and rarely useful to the agent.
_PRUNE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".next",
}


def get_tree(root_path: Path | str, max_depth: int = 3) -> str:
    """Return a textual tree of `root_path` up to `max_depth` levels deep.

    Output mirrors `tree(1)`:

        root_dir/
        ├── file_a.py
        ├── sub/
        │   ├── file_b.py
        │   └── file_c.py
        └── file_d.md
    """
    root_path = Path(root_path)

    if not root_path.exists():
        return f"(path not found: {root_path})"

    if root_path.is_file():
        return root_path.name

    lines = [f"{root_path.name}/"]
    _walk(root_path, "", lines, max_depth, depth=0)
    return "\n".join(lines)


def _walk(path: Path, prefix: str, out: list[str], max_depth: int, depth: int):
    if depth >= max_depth:
        return

    try:
        entries = sorted(
            [
                p for p in path.iterdir()
                if p.name not in _PRUNE and not p.name.startswith(".")
            ],
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError:
        return

    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        
        connector = "└── " if last else "├── "
        suffix = "/" if entry.is_dir() else ""

        out.append(f"{prefix}{connector}{entry.name}{suffix}")

        if entry.is_dir():
            extension = "    " if last else "│   "
            _walk(entry, prefix + extension, out, max_depth, depth + 1)
