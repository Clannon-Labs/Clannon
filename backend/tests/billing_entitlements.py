"""Fixed billing periods, mock settlement, and coarse token admission."""

from __future__ import annotations

import importlib
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


_SECRET = "test-only-billing-secret"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from api import config, run_driver, run_store
    import api.runs as runs_mod
    import api.run_revision as revision_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "billing.db"))
    monkeypatch.setattr(config, "DEFAULT_PLAN", "free")
    monkeypatch.setattr(config, "MOCK_BILLING_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "MOCK_BILLING_SECRET", _SECRET, raising=False)

    store = run_store.RunStore()
    monkeypatch.setattr(run_store, "STORE", store)
    monkeypatch.setattr(runs_mod, "STORE", store)
    monkeypatch.setattr(run_driver, "STORE", store)
    monkeypatch.setattr(revision_mod.runs, "STORE", store)

    executions = []

    def capture_execute(run, input_files=None):
        executions.append(run.id)

        async def complete():
            return None

        return complete()

    monkeypatch.setattr(runs_mod, "execute", capture_execute)
    app_mod = importlib.import_module("api.app")
    app_mod._auth_attempts.clear()
    client = TestClient(app_mod.app)
    owner = _signup(client, "owner@billing.example.com")
    return SimpleNamespace(
        app_mod=app_mod,
        client=client,
        owner=owner,
        store=store,
        executions=executions,
        monkeypatch=monkeypatch,
    )


def _signup(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/signup",
        json={"name": "Billing Owner", "email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _set_now(monkeypatch, value: datetime) -> None:
    from api import billing

    monkeypatch.setattr(billing, "utc_now", lambda: value)


def _set_signup(user_id: str, value: datetime, *, plan: str | None = None) -> None:
    from api import auth

    with auth._db() as db:
        db.execute(
            "UPDATE users SET created_at=?, plan=COALESCE(?, plan) WHERE id=?",
            (value.timestamp(), plan, user_id),
        )


def _persist_usage(env, user_id: str, tokens: int, created_at: str):
    run = env.store.create(user_id, "metered work")
    run.created_at = created_at
    run.tokens_used = tokens
    run.status = "delivered"
    env.store.persist(run)
    return run


def _checkout(client: TestClient, body: dict) -> dict:
    response = client.post("/billing/checkout", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _confirm(client: TestClient, checkout_id: str, confirmation_id: str, outcome: str):
    return client.post(
        "/billing/mock/confirm",
        headers={"X-Clannon-Mock-Billing-Secret": _SECRET},
        json={
            "checkoutId": checkout_id,
            "confirmationId": confirmation_id,
            "outcome": outcome,
        },
    )


def test_jan_31_anchor_clamps_and_recovers_across_leap_and_common_years():
    from api.billing import billing_period

    assert billing_period(date(2023, 1, 31), date(2023, 2, 27)) == (
        date(2023, 1, 31), date(2023, 2, 28)
    )
    assert billing_period(date(2023, 1, 31), date(2023, 2, 28)) == (
        date(2023, 2, 28), date(2023, 3, 31)
    )
    assert billing_period(date(2024, 1, 31), date(2024, 2, 29)) == (
        date(2024, 2, 29), date(2024, 3, 31)
    )
    assert billing_period(date(2024, 1, 31), date(2024, 3, 1)) == (
        date(2024, 2, 29), date(2024, 3, 31)
    )


def test_boundaries_stay_fixed_on_adjacent_days_inside_one_period():
    from api.billing import billing_period

    expected = (date(2026, 2, 28), date(2026, 3, 31))
    assert billing_period(date(2025, 1, 31), date(2026, 3, 1)) == expected
    assert billing_period(date(2025, 1, 31), date(2026, 3, 2)) == expected


def test_usage_counts_only_current_period_and_reports_additive_budget_fields(env):
    _set_signup(env.owner["id"], datetime(2025, 1, 31, tzinfo=timezone.utc))
    _set_now(env.monkeypatch, datetime(2026, 3, 15, 12, tzinfo=timezone.utc))
    _persist_usage(env, env.owner["id"], 11, "2026-02-27T23:59:59+00:00")
    _persist_usage(env, env.owner["id"], 20, "2026-02-28T00:00:00+00:00")
    _persist_usage(env, env.owner["id"], 30, "2026-03-14T12:00:00+00:00")
    _persist_usage(env, env.owner["id"], 99, "2026-03-31T00:00:00+00:00")

    usage = env.client.get("/usage").json()

    assert usage["periodStart"] == "2026-02-28"
    assert usage["periodEnd"] == "2026-03-31"
    assert usage["periodEndExclusive"] is True
    assert usage["used"] == 50
    assert usage["baseBudget"] == 100_000
    assert usage["additionalCredits"] == 0
    assert usage["budget"] == 100_000


def test_pending_failed_and_replayed_confirmation_never_grant_credit(env):
    _set_now(env.monkeypatch, datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
    checkout = _checkout(env.client, {"kind": "add_on", "creditAmount": 50_000})
    assert checkout["status"] == "pending"
    assert env.client.get("/usage").json()["additionalCredits"] == 0

    failed = _confirm(env.client, checkout["id"], "evt_failed_once", "failed")
    assert failed.status_code == 200, failed.text
    assert failed.json()["applied"] is False
    assert failed.json()["replayed"] is False
    assert env.client.get("/usage").json()["additionalCredits"] == 0

    replay = _confirm(env.client, checkout["id"], "evt_failed_once", "failed")
    assert replay.status_code == 200, replay.text
    assert replay.json()["applied"] is False
    assert replay.json()["replayed"] is True
    assert env.client.get("/usage").json()["additionalCredits"] == 0

    upgrade = _checkout(env.client, {"kind": "upgrade", "planId": "starter"})
    assert _confirm(env.client, upgrade["id"], "evt_failed_upgrade", "failed").status_code == 200
    assert env.client.get("/auth/me").json()["plan"] == "free"


def test_confirmed_credit_expands_budget_once_and_survives_store_reload(env):
    from api import run_driver, run_store
    import api.runs as runs_mod

    _set_now(env.monkeypatch, datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
    checkout = _checkout(env.client, {"kind": "add_on", "creditAmount": 75_000})
    first = _confirm(env.client, checkout["id"], "evt_credit_once", "confirmed")
    assert first.status_code == 200, first.text
    assert first.json()["applied"] is True
    replay = _confirm(env.client, checkout["id"], "evt_credit_once", "confirmed")
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True

    usage = env.client.get("/usage").json()
    assert usage["additionalCredits"] == 75_000
    assert usage["budget"] == usage["baseBudget"] + 75_000

    reloaded = run_store.RunStore()
    env.monkeypatch.setattr(run_store, "STORE", reloaded)
    env.monkeypatch.setattr(runs_mod, "STORE", reloaded)
    env.monkeypatch.setattr(run_driver, "STORE", reloaded)
    assert env.client.get("/usage").json()["additionalCredits"] == 75_000

    _set_now(env.monkeypatch, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
    assert env.client.get("/usage").json()["additionalCredits"] == 0


def test_upgrade_changes_only_checkout_owner_to_configured_plan(env):
    _set_signup(env.owner["id"], datetime(2025, 1, 31, tzinfo=timezone.utc))
    _set_now(env.monkeypatch, datetime(2026, 3, 15, 12, tzinfo=timezone.utc))
    other_client = TestClient(env.app_mod.app)
    other = _signup(other_client, "other@billing.example.com")
    checkout = _checkout(env.client, {"kind": "upgrade", "planId": "starter"})

    anonymous = TestClient(env.app_mod.app)
    anonymous_checkout = anonymous.post(
        "/billing/checkout", json={"kind": "add_on", "creditAmount": 1}
    )
    assert anonymous_checkout.status_code == 401
    assert anonymous.post("/billing/portal").status_code == 401
    assert anonymous.get(f"/billing/checkouts/{checkout['id']}").status_code == 401
    assert other_client.get(f"/billing/checkouts/{checkout['id']}").status_code == 404
    confirmed = _confirm(env.client, checkout["id"], "evt_upgrade_once", "confirmed")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["applied"] is True
    assert env.client.get("/auth/me").json()["plan"] == "starter"
    assert other_client.get("/auth/me").json()["plan"] == other["plan"] == "free"
    usage = env.client.get("/usage").json()
    assert (usage["periodStart"], usage["periodEnd"]) == ("2026-03-15", "2026-04-15")
    portal = env.client.post("/billing/portal")
    assert portal.status_code == 200
    assert portal.json()["planId"] == "starter"
    assert portal.json()["checkouts"][0]["id"] == checkout["id"]


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "upgrade", "planId": "definitely-not-configured"},
        {"kind": "add_on", "creditAmount": -1},
        {"kind": "add_on", "creditAmount": 10**30},
        {"kind": "add_on", "creditAmount": 10, "userId": "u_foreign"},
        {"kind": "upgrade", "planId": "starter", "price": 1},
        {"kind": "upgrade", "planId": "starter", "success": True},
    ],
)
def test_untrusted_checkout_values_are_rejected(env, body):
    assert env.client.post("/billing/checkout", json=body).status_code == 422


def test_mock_confirmation_requires_explicit_enablement_and_secret(env):
    checkout = _checkout(env.client, {"kind": "add_on", "creditAmount": 1})
    env.monkeypatch.setattr(importlib.import_module("api.config"), "MOCK_BILLING_ENABLED", False)
    assert _confirm(env.client, checkout["id"], "evt_disabled", "confirmed").status_code == 404

    env.monkeypatch.setattr(importlib.import_module("api.config"), "MOCK_BILLING_ENABLED", True)
    denied = env.client.post(
        "/billing/mock/confirm",
        headers={"X-Clannon-Mock-Billing-Secret": "wrong-secret"},
        json={
            "checkoutId": checkout["id"],
            "confirmationId": "evt_denied",
            "outcome": "confirmed",
        },
    )
    assert denied.status_code == 401
    assert env.client.get("/usage").json()["additionalCredits"] == 0

    env.monkeypatch.setattr(
        importlib.import_module("api.config"), "MOCK_BILLING_SECRET", None
    )
    unconfigured = _confirm(
        env.client, checkout["id"], "evt_unconfigured", "confirmed"
    )
    assert unconfigured.status_code == 503


def test_exhausted_root_followup_and_revision_create_nothing(env):
    _set_now(env.monkeypatch, datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
    exhausted = _persist_usage(
        env, env.owner["id"], 100_000, "2026-08-01T01:00:00+00:00"
    )
    before = {run.id for run in env.store.list_for(env.owner["id"], include_superseded=True)}

    root = env.client.post("/runs", data={"brief": "new root work"})
    followup = env.client.post(
        f"/runs/{exhausted.id}/followup", data={"brief": "continue work"}
    )
    revision = env.client.post(
        f"/runs/{exhausted.id}/revise",
        data={"brief": "replace work", "reuseInputs": "false"},
    )

    for response in (root, followup, revision):
        assert response.status_code == 402, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "token_budget_exhausted"
        assert detail["used"] == detail["budget"] == 100_000
        assert detail["periodEnd"]
        assert detail["actions"]
    after = {run.id for run in env.store.list_for(env.owner["id"], include_superseded=True)}
    assert after == before
    assert env.executions == []


def test_under_limit_user_proceeds(env):
    _set_now(env.monkeypatch, datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
    _persist_usage(env, env.owner["id"], 99_999, "2026-08-01T01:00:00+00:00")

    response = env.client.post("/runs", data={"brief": "one last admitted run"})

    assert response.status_code == 201, response.text
    assert env.store.get(env.owner["id"], response.json()["id"]) is not None
    assert env.executions == [response.json()["id"]]


def test_foreign_followup_and_revision_keep_non_disclosing_precedence(env):
    _set_now(env.monkeypatch, datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
    _persist_usage(env, env.owner["id"], 100_000, "2026-08-01T01:00:00+00:00")
    foreign_client = TestClient(env.app_mod.app)
    foreign = _signup(foreign_client, "foreign@billing.example.com")
    target = _persist_usage(env, foreign["id"], 1, "2026-08-01T02:00:00+00:00")
    before = {run.id for run in env.store.list_for(env.owner["id"], include_superseded=True)}

    followup = env.client.post(
        f"/runs/{target.id}/followup", data={"brief": "foreign followup"}
    )
    revision = env.client.post(
        f"/runs/{target.id}/revise",
        data={"brief": "foreign revision", "reuseInputs": "false"},
    )

    assert followup.status_code == 404
    assert revision.status_code == 404
    visible = env.store.list_for(env.owner["id"], include_superseded=True)
    assert {run.id for run in visible} == before


def test_unknown_server_plan_fails_closed_to_zero_entitlement(env):
    _set_signup(
        env.owner["id"],
        datetime(2026, 7, 15, tzinfo=timezone.utc),
        plan="corrupt-plan",
    )
    _set_now(env.monkeypatch, datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
    checkout = _checkout(env.client, {"kind": "add_on", "creditAmount": 50_000})
    assert _confirm(
        env.client, checkout["id"], "evt_corrupt_plan_credit", "confirmed"
    ).status_code == 200

    usage = env.client.get("/usage").json()
    assert usage["baseBudget"] == 0
    assert usage["additionalCredits"] == 0
    assert usage["budget"] == 0
    assert env.client.post("/runs", data={"brief": "must fail closed"}).status_code == 402
