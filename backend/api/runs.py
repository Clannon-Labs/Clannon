"""
Run execution + live streaming — FAÇADE.

The run subsystem was split into focused modules for modularity:

  - `run_state`  — the `RunState` record + its serialization + live event mappers.
  - `run_store`  — the in-memory live cache + SQLite persistence (`RunStore`, `STORE`).
  - `run_driver` — the execution path (`execute`, recovery, conversation replay,
                   model-override resolution).
  - `sse`        — `sse_stream`, the SSE transport.

This module is kept as a thin re-export surface so existing importers (e.g.
`api.app` using `runs.STORE` / `runs.execute` / `runs.sse_stream`, and tests
importing `RunState` / `build_model_overrides` / `_recover_from_filter_block`)
keep working unchanged. Put new run logic in the module it belongs to, not here.
"""

from __future__ import annotations

from .run_state import RunState
from .run_store import RunStore, STORE
from .run_driver import (
    build_model_overrides,
    execute,
    _build_conversation,
    _recover_from_filter_block,
)
from .sse import sse_stream

__all__ = [
    "RunState",
    "RunStore",
    "STORE",
    "build_model_overrides",
    "execute",
    "_build_conversation",
    "_recover_from_filter_block",
    "sse_stream",
]
