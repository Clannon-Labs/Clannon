"""Registry module discovery.

The registry is decorator-driven, so tools and experts exist only after Python
imports their modules. This file finds likely capability modules while avoiding
runtime data folders, virtualenvs, caches, tests, and archived legacy code.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from get_root import root

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = {
    ".agents",
    ".architecture",
    ".codex",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "assets",
    "legacy_capabilities_backup",
    "tests",
    "venv",
}

EXCLUDED_ROOT_DIRS = {
    "memory",
}

EXCLUDED_FILES = {
    "main.py",
}

EXCLUDED_MODULES = {
    "src.agent.loop",
}


def discover_registry_modules(project_root: Path | None = None) -> list[tuple[str, Exception]]:
    """Import project modules so @tool/@expert decorators can populate Registry.

    Registration is intentionally decorator-driven, so Python has to import a
    module before its decorators run. Discovery walks project Python files and
    imports importable modules without requiring the agent bootstrap to know
    where tools or experts live.

    Modules with broken optional dependencies are skipped and reported. A broken
    draft should not prevent unrelated enabled tools from registering.
    """
    base = project_root or root.project
    errors: list[tuple[str, Exception]] = []

    for module_name in iter_project_module_names(base):
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            errors.append((module_name, exc))
            logger.debug("Skipping registry discovery module %s: %s", module_name, exc)

    return errors


def iter_project_module_names(project_root: Path) -> list[str]:
    """Return importable module names that look like registry capability modules."""
    module_names: list[str] = []

    for path in sorted(project_root.rglob("*.py")):
        if should_skip_path(project_root, path):
            continue

        module_name = module_name_from_path(project_root, path)
        if module_name and module_name not in EXCLUDED_MODULES:
            module_names.append(module_name)

    return module_names


def should_skip_path(project_root: Path, path: Path) -> bool:
    """Decide whether a Python file should be ignored during discovery."""
    relative = path.relative_to(project_root)
    if path.name in EXCLUDED_FILES:
        return True
    if relative.parts and relative.parts[0] in EXCLUDED_ROOT_DIRS:
        return True
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    return not looks_like_registry_module(path)


def looks_like_registry_module(path: Path) -> bool:
    """Check source text for registry imports plus @tool/@expert decorators.

    Basic capability modules may use the public shorthand
    ``from registry import tool``. Primitive or internal modules may still use
    ``from registry.register import tool``. Discovery accepts both forms so the
    authoring import can stay small without hiding advanced registration paths.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    imports_registry_decorator = (
        "from registry.register import" in text
        or "import registry.register" in text
        or "from registry import" in text
    )
    uses_registry_decorator = "@tool" in text or "@expert" in text
    return imports_registry_decorator and uses_registry_decorator


def module_name_from_path(project_root: Path, path: Path) -> str | None:
    """Convert a project-relative Python path into an import module name."""
    relative = path.relative_to(project_root).with_suffix("")
    parts = relative.parts

    if not parts:
        return None

    if parts[-1] == "__init__":
        parts = parts[:-1]

    if not parts:
        return None

    return ".".join(parts)
