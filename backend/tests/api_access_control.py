"""
Hermetic API access-control regression harness -- OWASP API #1 BOLA/IDOR.

Drives api/app.py through a TestClient with TWO distinct authenticated users
and pins the multi-tenant authorization boundary at the HTTP layer, above the
manager-door (PR #53) and pipeline (PR #54) isolation layers.

For every owner-scoped endpoint:
  (a) user B calling with user A's object ID is REFUSED (404/403 -- never the
      object, never a mutation of A's data)
  (b) the same endpoint with NO authenticated session is rejected (401/403)

For idempotent-204 DELETE endpoints (DELETE /projects, DELETE /sessions), the
cross-user check verifies A's data is UNCHANGED after B's call, since the
endpoint intentionally returns 204 even for non-owners (never-revealed semantics).

Prints a per-endpoint CROSS-USER-DENIED / UNAUTH-DENIED / LEAK result table with
a tenant-isolated / LEAK verdict. On any genuine cross-user read or mutation,
reports it as a REAL security gap and writes a needs-reviewer note to
~/.clannon_proposal before failing the test.

Note: GET /memory/{entry_id} does not exist in the current API (app.py exposes
GET /memory for list and PUT/DELETE /memory/{entry_id} for write operations).
Only the endpoints that actually exist are tested.

Pins Critical Benchmark 5 (security) + Critical Benchmark 1 (memory scoping)
at the HTTP layer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: isolated DB + fresh RunStore -- mirrors tests/projects.py exactly
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from api import config, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)
    yield


# ---------------------------------------------------------------------------
# Main regression test
# ---------------------------------------------------------------------------


def test_api_access_control_bola_idor(db):
    """
    BOLA/IDOR regression: every owner-scoped endpoint refuses cross-user access
    and rejects unauthenticated callers. Collects all results before asserting
    so the full table is always printed even when a LEAK is found.
    """
    from api.app import app
    from api.runs import STORE

    # Three clients: Alice (user A), Bob (user B), anonymous (no session cookie).
    alice = TestClient(app)
    bob = TestClient(app)
    anon = TestClient(app)

    # --- sign up both users (cookies are retained by each TestClient) ---

    a_resp = alice.post(
        "/auth/signup",
        json={"name": "Alice", "email": "alice@fixture.com", "password": "password123"},
    )
    assert a_resp.status_code == 200, f"Alice signup failed: {a_resp.text}"
    a_id = a_resp.json()["id"]

    b_resp = bob.post(
        "/auth/signup",
        json={"name": "Bob", "email": "bob@fixture.com", "password": "password123"},
    )
    assert b_resp.status_code == 200, f"Bob signup failed: {b_resp.text}"

    # --- create Alice's resources ---

    # Project
    r = alice.post("/projects", json={"name": "Alice Corp"})
    assert r.status_code == 201, f"Alice project create failed: {r.text}"
    a_project_id = r.json()["id"]

    # Wiki entry
    r = alice.post(
        "/memory",
        json={"tier": "wiki", "title": "Alice Note", "content": "Alice secret content"},
    )
    assert r.status_code == 201, f"Alice wiki create failed: {r.text}"
    a_entry_id = r.json()["id"]

    # Run (injected directly -- no pipeline, no LLM)
    a_run = STORE.create(a_id, "Alice research brief")
    a_run.status = "delivered"
    a_run.artifacts = [
        {"id": "art_alice_01", "name": "alice_report.md", "mime": "text/markdown"}
    ]
    a_run.memory_writes = [{"content": "Alice secret fact", "ts": "2026-06-23T00:00:00+00:00"}]
    STORE.persist(a_run)   # writes to SQLite; removes from live cache
    a_run_id = a_run.id
    a_session_id = a_run.session_id    # equals a_run_id for a root turn

    # Bob's matching resources (needed for project/session fixture symmetry; not used as targets)
    b_run = STORE.create(b_resp.json()["id"], "Bob research brief")
    b_run.status = "delivered"
    STORE.persist(b_run)

    # --- assertion harness ---

    rows: list[tuple[str, str, str, str]] = []
    leaks: list[dict] = []

    def _check(
        label: str,
        b_call,         # callable -> httpx.Response  (B uses A's object ID)
        unauth_call,    # callable -> httpx.Response  (no session cookie)
        cross_check=None,  # callable(b_resp) -> (ok: bool, cross_label: str)
                           # When None: status in {403, 404} is the acceptance criterion.
    ):
        b_resp = b_call()
        unauth_resp = unauth_call()

        # Cross-user verdict
        if cross_check is not None:
            cross_ok, cross_label = cross_check(b_resp)
        else:
            cross_ok = b_resp.status_code in {403, 404}
            cross_label = (
                "CROSS-USER-DENIED"
                if cross_ok
                else f"LEAK({b_resp.status_code})"
            )

        # Unauthenticated verdict
        unauth_ok = unauth_resp.status_code in {401, 403}
        unauth_label = (
            "UNAUTH-DENIED" if unauth_ok else f"LEAK({unauth_resp.status_code})"
        )

        verdict = "tenant-isolated" if (cross_ok and unauth_ok) else "LEAK"
        rows.append((label, cross_label, unauth_label, verdict))
        if verdict == "LEAK":
            leaks.append(
                {
                    "endpoint": label,
                    "b_status": b_resp.status_code,
                    "unauth_status": unauth_resp.status_code,
                    "cross_label": cross_label,
                    "unauth_label": unauth_label,
                }
            )

    # --- endpoint checks ---

    # PUT /memory/{entry_id}
    # auth.wiki_update(b_id, a_entry_id, ...) -> WHERE id=? AND user_id=b -> 0 rows -> 404
    _check(
        "PUT /memory/{entry_id}",
        lambda: bob.put(
            f"/memory/{a_entry_id}",
            json={"tier": "wiki", "title": "HACKED", "content": "Bob was here"},
        ),
        lambda: anon.put(
            f"/memory/{a_entry_id}",
            json={"tier": "wiki", "title": "HACKED", "content": "x"},
        ),
    )

    # DELETE /memory/{entry_id}
    # forget_memory_write(b_id, a_entry_id) -> False (wiki id, not episodic);
    # wiki_delete(b_id, a_entry_id) -> WHERE id=? AND user_id=b -> 0 rows -> 404
    _check(
        "DELETE /memory/{entry_id}",
        lambda: bob.delete(f"/memory/{a_entry_id}"),
        lambda: anon.delete(f"/memory/{a_entry_id}"),
    )

    # GET /runs/{run_id}
    # STORE.get(b_id, a_run_id) -> None -> 404
    _check(
        "GET /runs/{run_id}",
        lambda: bob.get(f"/runs/{a_run_id}"),
        lambda: anon.get(f"/runs/{a_run_id}"),
    )

    # POST /runs/{run_id}/cancel
    # STORE.request_cancel(b_id, a_run_id) -> "notfound" -> 404
    _check(
        "POST /runs/{run_id}/cancel",
        lambda: bob.post(f"/runs/{a_run_id}/cancel"),
        lambda: anon.post(f"/runs/{a_run_id}/cancel"),
    )

    # POST /runs/{run_id}/feedback
    # STORE.set_feedback(b_id, a_run_id, ...) -> 0 rows -> False -> 404
    _check(
        "POST /runs/{run_id}/feedback",
        lambda: bob.post(
            f"/runs/{a_run_id}/feedback",
            json={"rating": "down", "comment": "Bob's graffiti"},
        ),
        lambda: anon.post(
            f"/runs/{a_run_id}/feedback",
            json={"rating": "down", "comment": "anon graffiti"},
        ),
    )

    # POST /runs/{run_id}/followup
    # STORE.get(b_id, a_run_id) -> None -> 404 before any pipeline starts
    _check(
        "POST /runs/{run_id}/followup",
        lambda: bob.post(
            f"/runs/{a_run_id}/followup",
            data={"brief": "Bob followup attempt"},
        ),
        lambda: anon.post(
            f"/runs/{a_run_id}/followup",
            data={"brief": "anon followup attempt"},
        ),
    )

    # GET /runs/{run_id}/thread
    # STORE.get(b_id, a_run_id) -> None -> 404
    _check(
        "GET /runs/{run_id}/thread",
        lambda: bob.get(f"/runs/{a_run_id}/thread"),
        lambda: anon.get(f"/runs/{a_run_id}/thread"),
    )

    # GET /runs/{run_id}/stream
    # STORE.get(b_id, a_run_id) -> None -> 404 before StreamingResponse is created
    _check(
        "GET /runs/{run_id}/stream",
        lambda: bob.get(f"/runs/{a_run_id}/stream"),
        lambda: anon.get(f"/runs/{a_run_id}/stream"),
    )

    # GET /runs/{run_id}/artifacts/{name}
    # STORE.get(b_id, a_run_id) -> None -> 404 before any file is read
    _check(
        "GET /runs/{run_id}/artifacts/{name}",
        lambda: bob.get(f"/runs/{a_run_id}/artifacts/alice_report.md"),
        lambda: anon.get(f"/runs/{a_run_id}/artifacts/alice_report.md"),
    )

    # DELETE /projects/{project_id}
    # Intentionally idempotent-204 (never-revealed semantics). The cross-user check
    # is DATA INTEGRITY: A's project must still exist after B's call.
    # delete_project(b_id, a_project_id) -> scoped to b_id -> 0 rows deleted -> A's project intact.
    def _project_cross_check(b_resp):
        if b_resp.status_code != 204:
            return False, f"UNEXPECTED-STATUS({b_resp.status_code})"
        # Confirm A's project still exists from Alice's perspective
        still_there = any(
            p["id"] == a_project_id for p in alice.get("/projects").json()
        )
        return (
            (True, "CROSS-USER-DENIED(204,no-mutation)")
            if still_there
            else (False, "LEAK(204,A-project-deleted)")
        )

    _check(
        "DELETE /projects/{project_id}",
        lambda: bob.delete(f"/projects/{a_project_id}"),
        lambda: anon.delete(f"/projects/{a_project_id}"),
        cross_check=_project_cross_check,
    )

    # DELETE /sessions/{session_id}
    # Intentionally idempotent-204 (never-revealed semantics). The cross-user check
    # is DATA INTEGRITY: A's run (= A's session root) must still exist after B's call.
    # delete_session(b_id, a_session_id) -> scoped to b_id -> 0 rows deleted -> A's run intact.
    def _session_cross_check(b_resp):
        if b_resp.status_code != 204:
            return False, f"UNEXPECTED-STATUS({b_resp.status_code})"
        # Confirm A's run still exists from Alice's perspective
        run_ok = alice.get(f"/runs/{a_run_id}").status_code == 200
        return (
            (True, "CROSS-USER-DENIED(204,no-mutation)")
            if run_ok
            else (False, "LEAK(204,A-session-deleted)")
        )

    _check(
        "DELETE /sessions/{session_id}",
        lambda: bob.delete(f"/sessions/{a_session_id}"),
        lambda: anon.delete(f"/sessions/{a_session_id}"),
        cross_check=_session_cross_check,
    )

    # --- print results table ---

    col_widths = [
        max(len(r[i]) for r in rows + [("Endpoint", "CROSS-USER", "UNAUTH", "Verdict")])
        for i in range(4)
    ]
    hdr = (
        f"{'Endpoint':<{col_widths[0]}}  "
        f"{'CROSS-USER':<{col_widths[1]}}  "
        f"{'UNAUTH':<{col_widths[2]}}  "
        f"{'Verdict':<{col_widths[3]}}"
    )
    div = "-" * len(hdr)

    print()
    print("API Access-Control (BOLA/IDOR) Regression -- HTTP boundary, per-endpoint")
    print(div)
    print(hdr)
    print(div)
    for row in rows:
        print(
            f"{row[0]:<{col_widths[0]}}  "
            f"{row[1]:<{col_widths[1]}}  "
            f"{row[2]:<{col_widths[2]}}  "
            f"{row[3]:<{col_widths[3]}}"
        )
    print(div)
    overall = (
        "TENANT-ISOLATED (all endpoints)"
        if not leaks
        else f"LEAK DETECTED ({len(leaks)} endpoint(s))"
    )
    print(f"Overall: {overall}")
    print()

    # --- write needs-reviewer note and fail on any genuine LEAK ---

    if leaks:
        note_path = "/home/amrit/.clannon_proposal"
        lines = [
            "needs-reviewer: API access-control LEAK detected",
            "",
            "The API access-control regression harness (tests/api_access_control.py)",
            "detected a genuine cross-tenant authorization failure at the HTTP layer.",
            "This is an OWASP API Security Top 10 #1 (BOLA/IDOR) violation.",
            "",
            "Affected endpoints:",
        ]
        for leak in leaks:
            lines.append(f"  - {leak['endpoint']}")
            lines.append(f"    cross-user result: {leak['cross_label']}")
            lines.append(f"    unauth result:     {leak['unauth_label']}")
        lines += [
            "",
            "Problem:",
            "  An authenticated second user (B) can read or mutate user A's resources",
            "  through an owner-scoped endpoint. The identity set at auth.current_user",
            "  (invariant SS-IV.18) is not being threaded into the store/auth call",
            "  for at least one endpoint, allowing cross-tenant data access.",
            "",
            "Options:",
            "  1. Audit the affected endpoint(s): confirm user_id flows from",
            "     auth.current_user (via Depends) into every STORE.get / auth.* call,",
            "     never from the request path/body. Minimal targeted fix.",
            "  2. Add a shared _require_ownership(user_id, resource_id) guard that",
            "     fails closed and is unit-tested independently.",
            "  3. Enable Supabase Row-Level Security (SET LOCAL, per-transaction) as",
            "     the enforcement layer so scoping cannot be omitted at the route layer.",
            "",
            "Recommendation: Option 1 (targeted fix at the failing endpoint(s));",
            "Option 3 when Supabase lands per the production roadmap.",
        ]
        try:
            with open(note_path, "w") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError:
            pass  # best-effort -- the pytest.fail below is the authoritative signal

        pytest.fail(
            f"SECURITY: {len(leaks)} cross-tenant authorization failure(s) detected "
            f"at the HTTP layer. Needs-reviewer note written to {note_path}. "
            "See printed table above for per-endpoint details."
        )
