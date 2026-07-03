"""
Hermetic tests for the production lifecycle endpoints and lifespan.

Covers:
  /health  — liveness probe: always 200, no dependency calls
  /ready   — readiness probe: 200 all-healthy / 503 any-down, per-dep body, no user data
  lifespan startup  — warmup() is invoked (spy double, no models loaded)
  lifespan shutdown — in-flight run-task double is cancelled within bounded drain

No network, no paid keys, no Qdrant, no embedding model downloads.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────


def _async_val(v: str):
    """Returns an async function that resolves to v — for patching async probes."""

    async def _f() -> str:
        return v

    return _f


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Fresh RunStore + throwaway DB per test; prevents cross-test state bleed."""
    from api import config, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    fresh = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", fresh)
    monkeypatch.setattr(runs_mod, "STORE", fresh)
    return fresh


@pytest.fixture()
def noop_warmup(monkeypatch):
    """Replaces warmup() with a no-op; returns the call list so tests can assert it ran."""
    import core.warmup as wm

    calls: list[bool] = []

    async def _noop() -> None:
        calls.append(True)

    monkeypatch.setattr(wm, "warmup", _noop)
    return calls


@pytest.fixture()
def probes(monkeypatch):
    """Returns a configure(**kwargs) callable that patches the three _health probe functions.
    Default values are all 'up'; pass a dep name as a keyword to override."""
    import api._health as hmod

    def configure(*, qdrant: str = "up", embeddings: str = "up", db: str = "up") -> None:
        monkeypatch.setattr(hmod, "probe_qdrant", _async_val(qdrant))
        monkeypatch.setattr(hmod, "probe_embeddings", lambda: embeddings)
        monkeypatch.setattr(hmod, "probe_db", lambda: db)

    return configure


# ── /health tests ─────────────────────────────────────────────────────────────


def test_health_200_whenever_process_is_up(store):
    """/health returns 200 + {status: ok} with no deps or auth."""
    from api.app import app

    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_never_calls_any_dependency(store, monkeypatch):
    """/health must be cheap: reaching any dependency probe is a test failure."""
    import api._health as hmod

    sentinel = []
    monkeypatch.setattr(hmod, "probe_qdrant", _async_val("should-not-be-called"))
    monkeypatch.setattr(hmod, "probe_embeddings", lambda: sentinel.append("embeddings") or "up")
    monkeypatch.setattr(hmod, "probe_db", lambda: sentinel.append("db") or "up")

    from api.app import app

    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert sentinel == [], f"/health called dependency probes: {sentinel}"


# ── /ready tests ──────────────────────────────────────────────────────────────


def test_ready_200_when_all_deps_healthy(store, probes):
    probes(qdrant="up", embeddings="up", db="up")
    from api.app import app

    resp = TestClient(app).get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["deps"] == {"qdrant": "up", "embeddings": "up", "db": "up"}


@pytest.mark.parametrize("dep", ["qdrant", "embeddings", "db"])
def test_ready_503_when_dep_is_down(dep, store, probes):
    probes(**{dep: "down"})
    from api.app import app

    resp = TestClient(app).get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["deps"][dep] == "down"


def test_ready_body_has_only_status_and_deps_no_user_data(store, probes):
    """Body shape is exactly {status, deps}; no user/tenant/session fields."""
    probes()
    from api.app import app

    body = TestClient(app).get("/ready").json()
    assert set(body.keys()) == {"status", "deps"}
    assert set(body["deps"].keys()) == {"qdrant", "embeddings", "db"}
    for v in body["deps"].values():
        assert v in ("up", "down"), f"unexpected dep status: {v!r}"


# ── lifespan startup ──────────────────────────────────────────────────────────


def test_startup_invokes_warmup(store, noop_warmup):
    """Lifespan startup calls warmup() exactly once."""
    from api.app import app

    with TestClient(app):
        pass  # enter = startup, exit = shutdown
    assert noop_warmup == [True], "warmup() was not invoked during lifespan startup"


def test_startup_survives_warmup_timeout(store, monkeypatch):
    """A warmup that stalls past the timeout must NOT crash startup (best-effort contract)."""
    import core.warmup as wm
    import api.app as app_mod

    async def _slow_warmup() -> None:
        await asyncio.sleep(9999)

    monkeypatch.setattr(wm, "warmup", _slow_warmup)
    monkeypatch.setattr(app_mod, "_WARMUP_TIMEOUT_S", 0.05)

    from api.app import app

    with TestClient(app):  # if startup crashes on TimeoutError the enter raises
        pass               # reaching here proves the lifespan handled it gracefully


# ── lifespan shutdown drain ───────────────────────────────────────────────────


def test_shutdown_cancels_inflight_task_within_bounded_drain(store, noop_warmup):
    """Shutdown signals cancellation to every live run-task and drains within the timeout."""

    async def _go() -> None:
        from api.run_state import RunState
        from api.app import lifespan, app

        task = asyncio.create_task(asyncio.sleep(60))
        run = RunState(
            id="run_drain",
            user_id="u1",
            title="drain test",
            brief="drain",
            status="orchestrating",
            session_id="run_drain",
        )
        run.task = task
        store._runs[run.id] = run

        async with lifespan(app):
            pass  # startup then immediate shutdown

        assert task.cancelled(), "in-flight run-task was not cancelled during shutdown drain"

    asyncio.run(asyncio.wait_for(_go(), timeout=15))


def test_shutdown_noop_when_no_live_runs(store, noop_warmup):
    """Shutdown with an empty store completes without error."""
    from api.app import app

    with TestClient(app):
        pass  # store is empty; shutdown must be a clean no-op


# ── summary table ─────────────────────────────────────────────────────────────


def test_summary_table(store, noop_warmup, probes, monkeypatch):
    """
    Runs every probe scenario and prints a HEALTHY / DEGRADED / STARTUP-WARMED /
    SHUTDOWN-DRAINED table for operator review.
    Fails if any cell is not one of the expected values.
    """
    from api.app import app

    rows: list[tuple[str, str]] = []

    # -- liveness --
    probes()
    r = TestClient(app).get("/health")
    rows.append(("/health liveness", "HEALTHY" if r.status_code == 200 else "FAIL"))

    # -- readiness all-up --
    probes(qdrant="up", embeddings="up", db="up")
    r = TestClient(app).get("/ready")
    rows.append(("/ready all deps up", "HEALTHY" if r.status_code == 200 else "FAIL"))

    # -- readiness per-dep degraded --
    for dep in ("qdrant", "embeddings", "db"):
        probes(**{dep: "down"})
        r = TestClient(app).get("/ready")
        rows.append((f"/ready {dep} down", "DEGRADED" if r.status_code == 503 else "FAIL"))

    # -- startup warmed --
    probes()
    with TestClient(app):
        pass
    rows.append(("startup warmup invoked", "STARTUP-WARMED" if noop_warmup else "FAIL"))

    # -- shutdown drain --
    drain_ok = [False]

    async def _drain_check() -> None:
        from api.run_state import RunState
        from api.app import lifespan

        task = asyncio.create_task(asyncio.sleep(60))
        run = RunState(
            id="run_tbl",
            user_id="u1",
            title="t",
            brief="b",
            status="orchestrating",
            session_id="run_tbl",
        )
        run.task = task
        store._runs[run.id] = run
        async with lifespan(app):
            pass
        drain_ok[0] = task.cancelled()

    asyncio.run(asyncio.wait_for(_drain_check(), timeout=15))
    rows.append(("shutdown in-flight drain", "SHUTDOWN-DRAINED" if drain_ok[0] else "FAIL"))

    # -- print table --
    w = max(len(label) for label, _ in rows)
    sep = "=" * (w + 24)
    print()
    print(sep)
    print(f"  {'Lifecycle probe':<{w}}  Result")
    print(sep)
    for label, result in rows:
        print(f"  {label:<{w}}  {result}")
    print(sep)

    assert all(result != "FAIL" for _, result in rows), (
        "one or more lifecycle probes produced FAIL — see table above"
    )
