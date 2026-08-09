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


@pytest.mark.parametrize("env", ["dev", "", "staging", "DEV"])
def test_dev_environments_get_the_log_mailer(monkeypatch, env):
    monkeypatch.setenv("CLANNON_ENV", env)
    monkeypatch.delenv("CLANNON_MAILER", raising=False)
    assert isinstance(resolve_mailer(), LogMailer)


@pytest.mark.parametrize("env", ["prod", "production", "PRODUCTION"])
def test_production_refuses_a_mailer_that_sends_nothing(monkeypatch, env):
    """The whole point of the guard: a private alpha nobody can join must fail loudly at
    startup, not quietly at the first signup."""
    monkeypatch.setenv("CLANNON_ENV", env)
    monkeypatch.setenv("CLANNON_MAILER", "log")
    with pytest.raises(MailError) as exc:
        resolve_mailer()
    assert "no email provider configured" in str(exc.value)


def test_unknown_mailer_fails_closed(monkeypatch):
    """An unrecognised value must not fall through to the no-op transport — a typo in
    deployment config would then silently disable all mail."""
    monkeypatch.setenv("CLANNON_ENV", "dev")
    monkeypatch.setenv("CLANNON_MAILER", "smtp")
    with pytest.raises(MailError):
        resolve_mailer()


def test_waitlist_config_bounds_are_enforced():
    """The config is the owner's control panel; an out-of-range value must fail at load
    rather than become a 300-day verification link."""
    from pydantic import ValidationError

    from settings import WAITLIST, WaitlistConfig

    assert WAITLIST.enabled is True
    assert 0 < WAITLIST.verify_token_ttl_hours <= 720
    with pytest.raises(ValidationError):
        WaitlistConfig(
            enabled=True, verify_token_ttl_hours=0, approval_token_ttl_hours=1,
            max_verification_sends_per_email=1, resend_cooldown_seconds=0, note_max_chars=1,
        )
