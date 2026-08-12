"""
The Mailer port and its dev transport.

The interesting behaviour here is not "can we send an email" — `LogMailer` sends
nothing by design. It is the **fail-closed guard**: a production deployment whose
verification mail silently goes to a log file would look identical, from the server's
side, to one that works, while nobody can actually join the private alpha. So the guard
that refuses to start is the thing worth pinning, and it is tested in both directions.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from core.mail import LogMailer, resolve_mailer
from foundation import Accepted, Mailer, MailError, Message


def _send(mailer, message):
    return asyncio.run(mailer.send(message))


def test_log_mailer_satisfies_the_port():
    """A transport that does not satisfy the Protocol would fail at the call site, far
    from here. Check the contract itself, so a signature change is caught at its source."""
    assert isinstance(LogMailer(), Mailer)


def test_send_accepts_and_records_without_delivering():
    mailer = LogMailer()
    out = _send(mailer, Message(to="tester@example.com", subject="Verify", text="link"))
    assert isinstance(out, Accepted)
    # No provider id, because no provider took it. `Accepted` deliberately does not mean
    # delivered, and a None id is the honest representation of "nothing sent it".
    assert out.provider_id is None
    assert [m.to for m in mailer.sent] == ["tester@example.com"]


@pytest.mark.parametrize("env", ["dev", "development", "test", "", "DEV"])
def test_dev_environments_get_the_log_mailer(monkeypatch, env):
    monkeypatch.setenv("CLANNON_ENV", env)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.delenv("CLANNON_MAILER", raising=False)
    assert isinstance(resolve_mailer(), LogMailer)


@pytest.mark.parametrize("env", ["prod", "production", "PRODUCTION"])
def test_production_refuses_a_mailer_that_sends_nothing(monkeypatch, env):
    """The whole point of the guard: a private alpha nobody can join must fail loudly at
    startup, not quietly at the first signup."""
    monkeypatch.setenv("CLANNON_ENV", env)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.setenv("CLANNON_MAILER", "log")
    with pytest.raises(MailError) as exc:
        resolve_mailer()
    assert "no email provider configured" in str(exc.value)


def test_unknown_mailer_fails_closed(monkeypatch):
    """An unrecognised value must not fall through to the no-op transport — a typo in
    deployment config would then silently disable all mail."""
    monkeypatch.setenv("CLANNON_ENV", "dev")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.setenv("CLANNON_MAILER", "smtp")
    with pytest.raises(MailError):
        resolve_mailer()


def test_waitlist_config_bounds_are_enforced():
    """The config is the owner's control panel; an out-of-range value must fail at load
    rather than become a 300-day verification link."""
    from pydantic import ValidationError

    import settings
    from settings import WaitlistConfig

    # Read the FILE, not the module attribute: conftest deliberately patches
    # settings.WAITLIST to enabled=False so the rest of the suite can use
    # POST /auth/signup. The thing worth pinning here is that the COMMITTED config
    # ships fail-closed, which a patched attribute cannot tell us.
    committed = settings._load_waitlist()
    assert committed.enabled is True, (
        "config/backend/waitlist.yaml must ship with the gate CLOSED — a config that "
        "ships open and relies on a deploy step to close it is fail-open"
    )
    assert 0 < committed.verify_token_ttl_hours <= 720
    with pytest.raises(ValidationError):
        WaitlistConfig(
            enabled=True, verify_token_ttl_hours=0, approval_token_ttl_hours=1,
            max_verification_sends_per_email=1, resend_cooldown_seconds=0, note_max_chars=1,
        )


# ---------------------------------------------------------------------------
# LAW 6 — the dependency lives behind ONE door, and that is enforced, not promised
# ---------------------------------------------------------------------------


def test_the_provider_is_named_in_exactly_one_module():
    """Owner's standing requirement: we must be able to swap the email provider by
    editing one place.

    A comment saying so decays; this fails the suite the moment a provider name leaks
    into `api/`, an expert, or anywhere else. If you are here because this went red,
    the fix is to route through `foundation.Mailer` / `resolve_mailer()`, not to widen
    the allowlist.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    allowed = {root / "core" / "mail.py", Path(__file__).resolve()}
    # Brand/SDK markers only. The bare word "resend" is deliberately NOT here: it is
    # also our own domain vocabulary (`POST /waitlist/resend`, `resend_cooldown_seconds`)
    # and matching it flagged nine innocent lines on the first run. A guard that cries
    # wolf gets widened until it means nothing, so it matches the provider's NAME and
    # its SDK, not an English verb we happen to share with it.
    pattern = re.compile(
        r"api\.resend\.com|resend\.com|RESEND_API_KEY|ResendMailer"
        r"|boto3|sendgrid|postmark|mailgun|ses_client|aiosmtplib",
        re.I,
    )

    offenders = []
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if ".venv" in parts or "__pycache__" in parts or path in allowed:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}")

    assert not offenders, (
        "email provider vocabulary escaped core/mail.py — the point of the Mailer port "
        f"is that exactly one file knows the provider:\n  " + "\n  ".join(offenders)
    )


def test_resend_is_selectable_and_fails_closed_on_missing_settings(monkeypatch):
    from core.mail import ResendMailer

    monkeypatch.setenv("CLANNON_ENV", "production")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.setenv("CLANNON_MAILER", "resend")

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("CLANNON_MAIL_FROM", "Clannon <hi@example.com>")
    with pytest.raises(MailError):
        resolve_mailer()

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("CLANNON_MAIL_FROM", raising=False)
    with pytest.raises(MailError):
        resolve_mailer()

    monkeypatch.setenv("CLANNON_MAIL_FROM", "Clannon <hi@example.com>")
    assert isinstance(resolve_mailer(), ResendMailer)


def _configure_production_mail(monkeypatch, *, mailer, api_key=None, sender=None):
    monkeypatch.setenv("CLANNON_ENV", "production")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.setenv("CLANNON_MAILER", mailer)
    for name, value in (
        ("RESEND_API_KEY", api_key),
        ("CLANNON_MAIL_FROM", sender),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("mailer", "api_key", "sender", "error"),
    [
        ("log", None, None, "no email provider configured"),
        ("smtp", None, None, "unknown mailer"),
        ("resend", None, "Clannon <hi@example.com>", "RESEND_API_KEY"),
        ("resend", "re_test_key", None, "CLANNON_MAIL_FROM"),
    ],
)
def test_production_lifespan_rejects_invalid_mail_before_warmup(
    monkeypatch, mailer, api_key, sender, error
):
    """Application must die before readiness, not wait for first waitlist send."""
    import core.warmup as warmup_mod
    from api.app import app

    _configure_production_mail(
        monkeypatch,
        mailer=mailer,
        api_key=api_key,
        sender=sender,
    )

    async def _must_not_warm() -> None:
        raise AssertionError("mail preflight must run before dependency warmup")

    monkeypatch.setattr(warmup_mod, "warmup", _must_not_warm)
    with pytest.raises(MailError, match=error):
        with TestClient(app):
            pass


def test_valid_production_mail_starts_without_network_io(monkeypatch):
    import core.mail as mail_mod
    import core.warmup as warmup_mod
    from api.app import app

    _configure_production_mail(
        monkeypatch,
        mailer="resend",
        api_key="re_test_key",
        sender="Clannon <hi@example.com>",
    )
    warmed = []

    async def _noop_warmup() -> None:
        warmed.append(True)

    def _network_forbidden(*_args, **_kwargs):
        raise AssertionError("startup mail preflight attempted network I/O")

    monkeypatch.setattr(warmup_mod, "warmup", _noop_warmup)
    monkeypatch.setattr(mail_mod.httpx, "AsyncClient", _network_forbidden)

    with TestClient(app):
        pass
    assert warmed == [True]


def test_resend_never_touches_the_network_without_config():
    """The transport must raise MailError, never leak an httpx exception class, so a
    caller cannot come to depend on the library we are isolating."""
    import httpx

    from core.mail import ResendMailer

    mailer = ResendMailer("re_key", "Clannon <hi@example.com>")

    class _Boom:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise httpx.ConnectError("no network")

    import core.mail as mail_mod
    original = mail_mod.httpx.AsyncClient
    mail_mod.httpx.AsyncClient = lambda *a, **k: _Boom()
    try:
        with pytest.raises(MailError):
            _send(mailer, Message(to="a@b.c", subject="s", text="t"))
    finally:
        mail_mod.httpx.AsyncClient = original
