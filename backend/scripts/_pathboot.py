"""
scripts/_pathboot.py

The one place every standalone demo script bootstraps `sys.path` so backend
imports (`foundation`, `core.memory`, ...) work regardless of the caller's
CWD (repo root or `backend/`) — LAW 1: this exact ~10-line block was
duplicated verbatim across `persistent_memory_demo.py`, `decision_memory_
demo.py`, and `cb2_repo_intelligence_demo.py` before being consolidated here.

No bootstrap-before-bootstrap problem: Python auto-adds a script's own
containing directory (`scripts/`) to `sys.path[0]` when it's run directly, so
`from _pathboot import ensure_backend_on_path` always resolves here first,
before backend/ itself is importable.
"""
from __future__ import annotations

import os
import sys


def ensure_backend_on_path() -> str:
    """Walk up from scripts/ until the directory containing foundation/ (the
    backend package root) is found, put it on sys.path if it isn't already,
    and return it — callers that need the backend root for their own path
    construction (e.g. pointing a repo walker at it) get it from the return
    value instead of re-deriving it. Idempotent — safe to call more than
    once."""
    here = os.path.abspath(os.path.dirname(__file__))
    backend = here
    while backend != os.path.dirname(backend):
        if os.path.isdir(os.path.join(backend, "foundation")):
            break
        backend = os.path.dirname(backend)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    return backend
