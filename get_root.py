"""
Locate the Vraksha project root from anywhere in the repo.

Walks upward from this file looking for project markers (.git, pyproject.toml,
requirements.txt, models.yaml, or a directory literally named "vraksha"). If no
marker is found it falls back to this file's own directory, so a valid Path is
always returned — never None.

Intended for top-level scripts/tools that need repo-relative paths without
depending on the current working directory. (Foundation modules deliberately do
not use this; they resolve their own paths to stay self-contained.)

Usage:
    from get_root import root
    models = root.project / "models.yaml"
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path


_MARKERS = (".git", "pyproject.toml", "requirements.txt", "models.yaml")


class ROOT:
    @cached_property
    def project(self) -> Path:
        """
        Absolute path to the project root.

        Anchored to this file's location (not the cwd) so it is stable wherever
        the process is launched from. Falls back to this file's own directory
        when no marker is found, so it never returns None.
        """
        here = Path(__file__).resolve()
        for parent in (here, *here.parents):
            if any((parent / marker).exists() for marker in _MARKERS):
                return parent
            if parent.name.lower() == "vraksha":
                return parent
        return here.parent

    @cached_property
    def system(self) -> Path:
        """Filesystem root that contains the project (e.g. '/' or 'C:\\')."""
        return Path(self.project.anchor)


root = ROOT()
