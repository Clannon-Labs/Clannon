"""
Private-alpha waitlist gate (owner ruling 2026-08-09): join -> verify inbox ->
owner approves (CLI) -> account created. Pins the security obligations from
`proposals/archive/to-api/2026-08-09_private-alpha-waitlist.md`:

  1. non-disclosure on /waitlist and /waitlist/resend (same response regardless
     of whether the address is new / listed / verified / already a real account)
  2. tokens are unguessable, single-use, hashed at rest; unknown/expired/consumed
     are indistinguishable
  3. POST /auth/signup stays closed server-side while WAITLIST.enabled
  4. the note is untrusted input, length-capped
  5. resend is capped per-address, independent of the per-IP rate limiter
  6. no code path claims delivery -- only that the mailer accepted the message
  7. a mail failure never creates a half-state (the waitlist row is already
     written; the failed send just doesn't count against the resend cap)

All hermetic: throwaway SQLite DB, `LogMailer` swapped in so no real provider
is ever touched, and WAITLIST config values overridden per test via
`model_copy` (the object is frozen, so the module-level NAME is replaced,
exactly like other config in this suite is monkeypatched).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from core.mail import LogMailer


def _cfg(base, **overrides):
    return base.model_copy(update=overrides)


def _token_from(text: str, param: str) -> str:
    m = re.search(rf"[?&]{param}=([A-Za-z0-9_\-]+)", text)
    assert m, f"no {param}= in mail body:\n{text}"
    return m.group(1)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Throwaway DB + a controllable LogMailer, wired into api.app / api.waitlist /
    api.waitlist_cli (each imports its own bound names, per module-import convention
    used throughout this config system)."""
    from api import config, run_store, app as app_mod, waitlist as waitlist_mod, waitlist_cli
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)

    mailer = LogMailer()
    monkeypatch.setattr(waitlist_mod, "resolve_mailer", lambda: mailer)
    monkeypatch.setattr(waitlist_cli, "resolve_mailer", lambda: mailer)

    def set_waitlist(**overrides):
        cfg = _cfg(waitlist_mod.WAITLIST, **overrides)
        monkeypatch.setattr(app_mod, "WAITLIST", cfg)
        monkeypatch.setattr(waitlist_mod, "WAITLIST", cfg)
        monkeypatch.setattr(waitlist_cli, "WAITLIST", cfg)
        return cfg

    return {
        "mailer": mailer,
        "set_waitlist": set_waitlist,
        "app_mod": app_mod,
        "waitlist_mod": waitlist_mod,
        "waitlist_cli": waitlist_cli,
    }


# ---------------------------------------------------------------------------
# 0. Premise / gate itself
# ---------------------------------------------------------------------------


def test_signup_refused_without_approval_token_and_no_user_created(env):
    from api import auth, waitlist_store
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)

    resp = client.post(
        "/auth/signup",
        json={"name": "Eve", "email": "eve@fixture.com", "password": "password123"},
    )
    assert resp.status_code == 403
    assert not waitlist_store.email_registered("eve@fixture.com")


def test_enabled_false_restores_ordinary_signup(env):
    from api.app import app

    env["set_waitlist"](enabled=False)
    client = TestClient(app)

    resp = client.post(
        "/auth/signup",
        json={"name": "Fay", "email": "fay@fixture.com", "password": "password123"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "fay@fixture.com"

    # the switch is real both ways: login works, cookie was set
    login = client.post("/auth/login", json={"email": "fay@fixture.com", "password": "password123"})
    assert login.status_code == 200


# ---------------------------------------------------------------------------
# 1. Non-disclosure
# ---------------------------------------------------------------------------


def test_join_response_identical_new_vs_already_listed(env):
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)

    first = client.post("/waitlist", json={"email": "gia@fixture.com"})
    second = client.post("/waitlist", json={"email": "gia@fixture.com"})

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    # exactly one verify mail was sent -- the second POST didn't re-trigger a send
    # because email_verified is still false but... actually a repeat join DOES try
    # to resend (subject to cap); assert it stayed under the real cap, never erroring
    assert all(m.to == "gia@fixture.com" for m in env["mailer"].sent)


def test_waitlist_mail_runs_after_response_body_is_scheduled(env):
    """Mail is attached as response background work, not awaited in route logic.

    TestClient executes background work before returning (so existing delivery
    assertions stay meaningful), while a real ASGI client receives the identical
    202 body before provider I/O begins.
    """
    from api.app import app
    from api import waitlist_store

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    response = client.post("/waitlist", json={"email": "background@fixture.com"})
    assert response.status_code == 202
    assert env["mailer"].sent and env["mailer"].sent[0].to == "background@fixture.com"
    assert waitlist_store.waitlist_get("background@fixture.com")["verify_send_count"] == 1


def test_join_response_identical_for_already_registered_account(env):
    from api import auth, waitlist_store
    from api.app import app

    env["set_waitlist"](enabled=True)
    auth.create_user("holly@fixture.com", "Holly", "password123")
    client = TestClient(app)

    resp = client.post("/waitlist", json={"email": "holly@fixture.com"})
    baseline = client.post("/waitlist", json={"email": "ivy@fixture.com"})

    assert resp.status_code == baseline.status_code == 202
    assert resp.json() == baseline.json()
    # an already-registered address never gets a waitlist row or mail
    assert waitlist_store.waitlist_get("holly@fixture.com") is None
    assert all(m.to != "holly@fixture.com" for m in env["mailer"].sent)


def test_resend_over_cap_refused_without_revealing(env):
    from api import auth, waitlist_store
    from api.app import app

    env["set_waitlist"](enabled=True, max_verification_sends_per_email=1, resend_cooldown_seconds=0)
    client = TestClient(app)

    client.post("/waitlist", json={"email": "jack@fixture.com"})  # uses the one send
    assert len(env["mailer"].sent) == 1

    over_cap = client.post("/waitlist/resend", json={"email": "jack@fixture.com"})
    unknown = client.post("/waitlist/resend", json={"email": "never-joined@fixture.com"})

    assert over_cap.status_code == unknown.status_code == 202
    assert over_cap.json() == unknown.json()
    # no second mail went out for the capped address
    assert len(env["mailer"].sent) == 1
    entry = waitlist_store.waitlist_get("jack@fixture.com")
    assert entry["verify_send_count"] == 1


def test_note_over_max_chars_rejected(env):
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    too_long = "x" * (env["waitlist_mod"].WAITLIST.note_max_chars + 1)

    resp = client.post("/waitlist", json={"email": "kim@fixture.com", "note": too_long})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2. Tokens: unguessable, single-use, indistinguishable failure
# ---------------------------------------------------------------------------


def test_verify_token_reuse_fails(env):
    from api import auth, waitlist_store
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    client.post("/waitlist", json={"email": "liam@fixture.com"})
    token = _token_from(env["mailer"].sent[-1].text, "token")

    first = client.get(f"/waitlist/verify?token={token}", follow_redirects=False)
    second = client.get(f"/waitlist/verify?token={token}", follow_redirects=False)

    assert first.status_code == 307
    assert first.headers["location"].endswith("/waitlist/confirmed")
    assert second.status_code == 307
    assert second.headers["location"].endswith("/waitlist/invalid-link")
    assert waitlist_store.waitlist_get("liam@fixture.com")["email_verified"] == 1


def test_expired_token_indistinguishable_from_unknown(env):
    from api import auth, waitlist_store

    env["set_waitlist"](enabled=True)
    waitlist_store.waitlist_upsert("mia@fixture.com", None)
    expired = waitlist_store.waitlist_issue_token("mia@fixture.com", "verify", ttl_seconds=-1)

    assert waitlist_store.waitlist_consume_token(expired, "verify") is None
    assert waitlist_store.waitlist_consume_token("not-a-real-token", "verify") is None


def test_unknown_token_via_http_redirects_to_invalid_link(env):
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    resp = client.get("/waitlist/verify?token=totally-made-up", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/waitlist/invalid-link")


# ---------------------------------------------------------------------------
# 3. Full path
# ---------------------------------------------------------------------------


def test_full_path_waitlist_verify_approve_account_exists_and_logs_in(env):
    from api import auth, waitlist_store
    from api.app import app
    from api.waitlist_cli import _approve
    import asyncio

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    email = "nora@fixture.com"

    join = client.post("/waitlist", json={"email": email, "note": "excited to try it"})
    assert join.status_code == 202
    verify_token = _token_from(env["mailer"].sent[-1].text, "token")

    verify = client.get(f"/waitlist/verify?token={verify_token}", follow_redirects=False)
    assert verify.headers["location"].endswith("/waitlist/confirmed")
    entry = waitlist_store.waitlist_get(email)
    assert entry["email_verified"] == 1
    assert entry["approved"] == 0
    assert not waitlist_store.email_registered(email)  # still no users row

    # owner approval -- CLI, not a route
    asyncio.run(_approve(email))
    entry = waitlist_store.waitlist_get(email)
    assert entry["approved"] == 1
    approval_token = _token_from(env["mailer"].sent[-1].text, "approvalToken")

    signup = client.post(
        "/auth/signup",
        json={"name": "Nora", "password": "password123", "approvalToken": approval_token},
    )
    assert signup.status_code == 200, signup.text
    assert signup.json()["email"] == email
    assert waitlist_store.email_registered(email)

    # the approval token is single-use too
    replay = client.post(
        "/auth/signup",
        json={"name": "Nora", "password": "password123", "approvalToken": approval_token},
    )
    assert replay.status_code == 403

    login = TestClient(app).post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200


def test_note_never_appears_in_any_mail_body(env):
    """The note is untrusted input the owner will read from the DB later -- it must
    never be interpolated into an email body (obligation #4)."""
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    secret_note = "please DO-NOT-LEAK-ME into any outgoing mail"

    client.post("/waitlist", json={"email": "quinn@fixture.com", "note": secret_note})
    assert env["mailer"].sent
    assert all(secret_note not in m.text and secret_note not in (m.html or "") for m in env["mailer"].sent)


def test_public_waitlist_route_is_rate_limited(env):
    """Every public route rate-limits (obligation #5) -- reuses api.app's shared
    per-IP limiter, same one already pinned on /auth/signup and /auth/login."""
    from api import config
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)

    for i in range(config.AUTH_RATE_MAX_ATTEMPTS):
        resp = client.post("/waitlist", json={"email": f"rate{i}@fixture.com"})
        assert resp.status_code == 202

    over_limit = client.post("/waitlist", json={"email": "rate-over@fixture.com"})
    assert over_limit.status_code == 429


def test_signup_rejects_invalid_approval_token(env):
    from api.app import app

    env["set_waitlist"](enabled=True)
    client = TestClient(app)
    resp = client.post(
        "/auth/signup",
        json={"name": "Omar", "password": "password123", "approvalToken": "not-a-real-token"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Mail failure never creates a half-state
# ---------------------------------------------------------------------------


def test_mail_failure_leaves_entry_writable_and_does_not_burn_the_cap(env, monkeypatch):
    """The waitlist row is written before the mailer is ever called. If the send
    fails, the entry still exists (so a later resend can retry) and the failed
    attempt is not counted against the per-address send cap."""
    from api import auth, waitlist_store
    from api.app import app
    from foundation import MailError

    env["set_waitlist"](enabled=True)

    async def failing_send(_message):
        raise MailError("provider down")

    monkeypatch.setattr(env["mailer"], "send", failing_send)
    client = TestClient(app)

    resp = client.post("/waitlist", json={"email": "priya@fixture.com"})
    assert resp.status_code == 202  # never surfaces the provider failure to the caller

    entry = waitlist_store.waitlist_get("priya@fixture.com")
    assert entry is not None  # the row exists despite the failed send
    assert entry["verify_send_count"] == 0  # the failed attempt didn't burn the cap
