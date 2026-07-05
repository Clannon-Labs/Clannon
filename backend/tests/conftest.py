"""Shared test isolation.

The auth and intake rate limiters are process-global in-memory state
(`api.app._auth_attempts`, the sliding-window singletons in
`core.intake.rate_limiter`). Every test runs in one process, so an auth-heavy
test file can silently exhaust the signup budget of every LATER file — the
victim then sees 429s masquerading as endpoint bugs (a real cross-file failure
this fixture was added to stop). Reset them before each test; tests that
exercise rate limiting do so within a single test (or on their own instances),
so a pre-test reset never weakens what they pin.
"""

import sys

import pytest

import core.memory.graph_store as _graph_store_mod


@pytest.fixture(autouse=True)
def _isolate_shared_rate_limits():
    app_mod = sys.modules.get("api.app")
    if app_mod is not None:
        getattr(app_mod, "_auth_attempts", {}).clear()
    rl_mod = sys.modules.get("core.intake.rate_limiter")
    if rl_mod is not None:
        for name in ("_identity_rate_limiter", "_global_rate_limiter"):
            limiter = getattr(rl_mod, name, None)
            if limiter is not None:
                limiter._requests.clear()
    yield


@pytest.fixture(autouse=True)
def _fresh_graph_store(tmp_path, monkeypatch):
    """Kuzu's db handle is a lazy module-level singleton (same shape as
    store.py's Qdrant client) — point it at a fresh on-disk db per test and
    reset it after, so no test sees another test's Kuzu state. Shared here
    (not per-file) so memory_graph_store.py and memory_graph_manager.py stop
    duplicating this fixture verbatim (LAW 1)."""
    monkeypatch.setenv("VRAKSHA_GRAPH_DB_PATH", str(tmp_path / "graph_db"))
    _graph_store_mod._db = None
    _graph_store_mod._conn = None
    _graph_store_mod._schema_ready = False
    _graph_store_mod.DISABLED = False
    yield
    _graph_store_mod._db = None
    _graph_store_mod._conn = None
    _graph_store_mod._schema_ready = False
