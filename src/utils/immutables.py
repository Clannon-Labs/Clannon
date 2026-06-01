"""Single source of truth for files the agent must never write to.

Used by:
- src.utils.changes  (text-parsed memory writes)
- src.utils.file_tools.write_file  (arbitrary file writes via tool)

The list lives in `memory/IMMUTABLE.yaml`. Match logic:
- Entries with "/" are project-root-relative path matches.
- Entries without "/" are bare filename matches (any depth).
"""

from pathlib import Path
import logging

import yaml

from get_root import root

logger = logging.getLogger(__name__)

_IMMUTABLES_PATH = root.project / "memory" / "IMMUTABLE.yaml"
_cache: list[str] | None = None


def _load() -> list[str]:
    global _cache

    if _cache is None:
        if not _IMMUTABLES_PATH.exists():
            logger.warning(
                f"⚠️  IMMUTABLE.yaml not found at {_IMMUTABLES_PATH} — "
                "no files will be protected"
            )
            _cache = []
            return _cache

        with open(_IMMUTABLES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        _cache = list(data.get("immutable", []))

    return _cache


def immutable_paths() -> list[str]:
    """Raw entries from IMMUTABLE.yaml, for display in prompts."""
    return list(_load())


def is_immutable(target: Path | str) -> bool:
    """True if writes to `target` should be refused."""
    if isinstance(target, str):
        target = Path(target)

    project = root.project.resolve()

    try:
        rel = target.resolve().relative_to(project).as_posix()
        
    except (ValueError, OSError):
        rel = target.as_posix()

    name = target.name

    for entry in _load():
        if "/" in entry:
            if rel == entry:
                return True
        else:
            if name == entry:
                return True
    return False
