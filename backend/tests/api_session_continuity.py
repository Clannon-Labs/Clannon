"""
Session-continuity contract harness — api/ HTTP boundary.

Pins three assertions the "second session is the magic" moat depends on:

  (a) SHARED-SESSION
      POST /runs/{id}/followup creates a new run that inherits the parent's
      session_id — a genuine continuation, not an orphan root turn.

  (b) THREAD-ORDERED
      GET /runs/{id}/thread returns every turn of that session oldest-first
      as one conversation, accessible from any turn in the session.

  (c) DELETE-SCOPED-MEMORY-KEPT
      DELETE /sessions/{id} removes all conversation turns (idempotent 204)
      while the user's cross-session learned memory (wiki entries, the
      highest-trust tier) is retained. This pins the documented
      "conversation gone, learned memory kept" split.

Hermetic: TestClient + in-memory RunStore + fresh SQLite DB per fixture.
No real model fires (execute is stubbed). Separate from:
  - tests/sessions_usage.py  (RunStore.delete_session at the DATA layer)
  - tests/message_channel.py (say-tool / message_delta, incidental session ref)

Serves Exceptional Benchmark 2 (Autonomous Project Continuity) and
Critical Benchmark 1 (Persistent Cross-Session Memory).
"""

import time
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated app client: fresh SQLite DB, fresh RunStore, no-op execute."""
    from api import config, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    # Continuity proof intentionally seeds wiki, which starts at starter.
    monkeypatch.setattr(config, "DEFAULT_PLAN", "starter")
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)

    async def _noop_execute(run, input_files=None):
        """Stub: no pipeline stages, no paid model calls."""

    monkeypatch.setattr(runs_mod, "execute", _noop_execute)

    from api.app import app
    yield TestClient(app, raise_server_exceptions=True), store


def _signup(client: TestClient, email: str, name: str = "User") -> dict:
    r = client.post(
        "/auth/signup",
        json={"name": name, "email": email, "password": "password123"},
    )
    assert r.status_code == 200, f"signup failed: {r.text}"
    return r.json()


def _seed_root(store, user_id: str, brief: str):
    """Create a completed root run directly in the store.

    The HTTP POST /runs route triggers execute() (even when stubbed it goes
    through the asyncio task machinery). Creating the root directly avoids
    multipart upload edge cases and keeps the fixture focused on the contract
    under test: session inheritance and thread ordering.
    """
    run = store.create(user_id, brief)
    run.status = "delivered"
    run.report = ""
    store.persist(run)
    return run


# ---------------------------------------------------------------------------
# assertion helpers — each returns (ok: bool, detail: str)
# ---------------------------------------------------------------------------


def _check_shared_session(client: TestClient, store) -> tuple[bool, str]:
    """(a) POST /runs/{id}/followup inherits the parent session_id."""
    me = _signup(client, "a_shared@x.io", "Alice")
    root = _seed_root(store, me["id"], "What is the capital of France?")
    root_id = root.id
    expected_session = root.session_id  # root turn owns its own session

    fu_r = client.post(
        f"/runs/{root_id}/followup",
        data={"brief": "Which river runs through it?"},
    )
    if fu_r.status_code != 201:
        return False, f"POST /followup returned {fu_r.status_code}: {fu_r.text}"
    fu_id = fu_r.json()["id"]

    fu = client.get(f"/runs/{fu_id}")
    if fu.status_code != 200:
        return False, f"GET /runs/{fu_id} returned {fu.status_code}"
    fu_j = fu.json()

    if fu_j["sessionId"] != expected_session:
        return False, (
            f"followup sessionId={fu_j['sessionId']!r} does not match parent "
            f"sessionId={expected_session!r}; followup opened an orphan root "
            "session instead of continuing the conversation"
        )
    if fu_j["parentRunId"] != root_id:
        return False, (
            f"parentRunId={fu_j['parentRunId']!r} does not point back to "
            f"the parent run {root_id!r}"
        )
    return True, (
        f"followup {fu_id} correctly inherits session_id={expected_session!r} "
        f"and records parentRunId={root_id!r}"
    )


def _check_thread_ordered(client: TestClient, store) -> tuple[bool, str]:
    """(b) GET /runs/{id}/thread returns all turns oldest-first."""
    me = _signup(client, "b_thread@x.io", "Bob")
    root = _seed_root(store, me["id"], "Turn one")
    time.sleep(0.003)  # ensure distinct created_at across turns

    fu1_r = client.post(f"/runs/{root.id}/followup", data={"brief": "Turn two"})
    if fu1_r.status_code != 201:
        return False, f"POST /followup (turn 2) returned {fu1_r.status_code}"
    fu1_id = fu1_r.json()["id"]
    time.sleep(0.003)

    fu2_r = client.post(f"/runs/{fu1_id}/followup", data={"brief": "Turn three"})
    if fu2_r.status_code != 201:
        return False, f"POST /followup (turn 3) returned {fu2_r.status_code}"
    fu2_id = fu2_r.json()["id"]

    expected = [root.id, fu1_id, fu2_id]

    # Thread accessible from root
    thread_r = client.get(f"/runs/{root.id}/thread")
    if thread_r.status_code != 200:
        return False, f"GET /thread returned {thread_r.status_code}: {thread_r.text}"
    turns = thread_r.json()
    ids = [t["id"] for t in turns]

    if len(turns) != 3:
        return False, f"expected 3 turns in thread, got {len(turns)}: {ids}"
    if ids != expected:
        return False, (
            f"thread is not oldest-first: expected {expected}, got {ids}"
        )

    # Thread also accessible from any other turn in the session
    thread_from_last = client.get(f"/runs/{fu2_id}/thread")
    if thread_from_last.status_code != 200:
        return False, (
            f"GET /thread from last turn returned {thread_from_last.status_code}"
        )
    if [t["id"] for t in thread_from_last.json()] != expected:
        return False, "thread order differs when requested from the last turn"

    return True, (
        f"3-turn thread {expected} is oldest-first, accessible from any turn"
    )


def _check_delete_scoped_memory_kept(client: TestClient, store) -> tuple[bool, str]:
    """(c) DELETE /sessions/{id} removes turns (idempotent 204); wiki survives."""
    me = _signup(client, "c_delete@x.io", "Carol")

    # Seed cross-session learned memory: a wiki entry (highest-trust tier)
    wiki_r = client.post(
        "/memory",
        json={
            "tier": "wiki",
            "title": "Design style",
            "content": "Prefer minimal, monochromatic layouts.",
        },
    )
    if wiki_r.status_code != 201:
        return False, f"POST /memory returned {wiki_r.status_code}: {wiki_r.text}"
    wiki_id = wiki_r.json()["id"]

    # Build a two-turn conversation
    root = _seed_root(store, me["id"], "Design a landing page")
    session_id = root.session_id  # == root.id for a root turn

    fu_r = client.post(f"/runs/{root.id}/followup", data={"brief": "Make it minimal"})
    if fu_r.status_code != 201:
        return False, f"POST /followup returned {fu_r.status_code}"
    fu_id = fu_r.json()["id"]

    # Sanity: thread has both turns before the delete
    pre_thread = client.get(f"/runs/{root.id}/thread").json()
    if len(pre_thread) != 2:
        return False, f"expected 2 turns before delete, got {len(pre_thread)}"

    # First delete
    del1 = client.delete(f"/sessions/{session_id}")
    if del1.status_code != 204:
        return False, (
            f"DELETE /sessions/{session_id} returned {del1.status_code} "
            f"(expected 204): {del1.text}"
        )

    # Idempotent: a second delete on an already-empty session is also 204
    del2 = client.delete(f"/sessions/{session_id}")
    if del2.status_code != 204:
        return False, (
            f"second DELETE /sessions/{session_id} returned {del2.status_code} "
            "(expected idempotent 204)"
        )

    # All conversation turns must be gone
    r_root = client.get(f"/runs/{root.id}")
    if r_root.status_code != 404:
        return False, (
            f"root run {root.id} still returns {r_root.status_code} after "
            "session delete (expected 404)"
        )
    r_fu = client.get(f"/runs/{fu_id}")
    if r_fu.status_code != 404:
        return False, (
            f"followup run {fu_id} still returns {r_fu.status_code} after "
            "session delete (expected 404)"
        )

    # Cross-session learned memory (wiki) must be retained — the split
    mem = client.get("/memory").json()
    wiki_ids = [m["id"] for m in mem if m.get("tier") == "wiki"]
    if wiki_id not in wiki_ids:
        return False, (
            f"wiki entry {wiki_id!r} was deleted alongside the conversation — "
            "the 'conversation gone, learned memory kept' split is VIOLATED"
        )

    return True, (
        f"session {session_id} deleted (idempotent); "
        f"wiki entry {wiki_id!r} retained"
    )


# ---------------------------------------------------------------------------
# individual tests — fast-fail per assertion for CI triage
# ---------------------------------------------------------------------------


def test_shared_session(env):
    """(a) followup inherits the parent's session_id at the HTTP boundary."""
    client, store = env
    ok, detail = _check_shared_session(client, store)
    assert ok, f"SHARED-SESSION VIOLATED: {detail}"


def test_thread_ordered(env):
    """(b) GET /runs/{id}/thread returns all turns oldest-first."""
    client, store = env
    ok, detail = _check_thread_ordered(client, store)
    assert ok, f"THREAD-ORDERED VIOLATED: {detail}"


def test_delete_scoped_memory_kept(env):
    """(c) DELETE /sessions/{id} clears turns; wiki memory survives."""
    client, store = env
    ok, detail = _check_delete_scoped_memory_kept(client, store)
    assert ok, f"DELETE-SCOPED-MEMORY-KEPT VIOLATED: {detail}"


# ---------------------------------------------------------------------------
# combined verdict table — runs all three, prints a report, fails if any violated
# ---------------------------------------------------------------------------


def test_session_continuity_contract(env):
    """
    Full session-continuity contract. Runs all three assertions on a shared
    hermetic environment, prints a per-assertion verdict table, and opens a
    needs-reviewer note on any genuine violation rather than patching a stage.
    """
    client, store = env

    checks = [
        ("SHARED-SESSION", _check_shared_session),
        ("THREAD-ORDERED", _check_thread_ordered),
        ("DELETE-SCOPED-MEMORY-KEPT", _check_delete_scoped_memory_kept),
    ]
    results: list[tuple[str, bool, str]] = []
    for label, fn in checks:
        try:
            ok, detail = fn(client, store)
        except Exception as exc:
            ok, detail = False, f"unexpected error: {exc}"
        results.append((label, ok, detail))

    all_ok = all(ok for _, ok, _ in results)
    verdict = "continuity held" if all_ok else "VIOLATED"

    lines = [
        "",
        "session-continuity contract",
        "-" * 68,
    ]
    for label, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        lines.append(f"  {mark}  {label:<30}  {detail}")
    lines += ["-" * 68, f"  Verdict: {verdict}", ""]
    report = "\n".join(lines)
    print(report)

    if not all_ok:
        violated = [
            f"  {label}: {detail}"
            for label, ok, detail in results
            if not ok
        ]
        note = (
            "[needs-reviewer] Session-continuity violations at api/ boundary\n"
            + "\n".join(violated)
            + "\n"
        )
        try:
            with open("/home/amrit/.clannon_proposal", "a") as fh:
                fh.write(note)
        except OSError:
            pass
        assert False, f"Session continuity VIOLATED — see printed table above"
