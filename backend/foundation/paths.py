"""
Project root resolution.

One import-location-independent way to find the repository/app root, so no module
has to guess its own depth with `Path(__file__).resolve().parents[N]` -- which
breaks the moment a file moves or the package is installed/vendored elsewhere.

`get_root()` anchors on THIS file (always inside the `foundation` package, which
sits directly under the root) and walks up to the nearest ancestor holding a
project marker, so the answer is the same no matter who calls it. The markers are
files that actually ship, so it also works in a stripped container where `.git`
is absent. `VRAKSHA_ROOT` overrides everything for unusual deploy layouts.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ROOT_ENV = "VRAKSHA_ROOT"
# Ordered by reliability; the first ancestor holding any of these is the root.
_MARKERS = ("pyproject.toml", "requirements.txt", "main.py", ".git")


@lru_cache(maxsize=1)
def get_root() -> Path:
    """The project root, resolved once and cached.

    Order: VRAKSHA_ROOT if set; else the nearest ancestor of this module that
    holds a project marker; else the package's parent (foundation/ sits directly
    under the root) as a safe fallback.
    """
    env = os.getenv(ROOT_ENV)
    if env:
        return Path(env).resolve()

    here = Path(__file__).resolve()
    for parent in here.parents:
        if any((parent / marker).exists() for marker in _MARKERS):
            return parent
    return here.parents[1]
