"""
Mailer implementations — the dev/default transport behind `foundation.Mailer`.

`LogMailer` is what runs until the owner provisions a real provider (account, API key,
and a sending domain with SPF/DKIM DNS records — the DNS part is what actually decides
whether verification mail reaches a stranger's inbox). It writes the message to the log
and accepts it.

**It is deliberately loud about being fake.** A dev transport that silently swallows
mail is how "the verification email never arrived" becomes a two-hour debugging session,
so every send logs at WARNING with the recipient and the fact that nothing was sent. It
also refuses to run in production: a real deployment quietly logging its verification
emails instead of sending them would let a private alpha look open while nobody can
actually get in. Fail closed (LAW 5).

Adding a real provider means one new class here and one line in `resolve_mailer` —
nothing outside this module and `foundation/contracts/mailer.py` learns the provider's
name.
"""

from __future__ import annotations

import logging
import os

import httpx

from foundation import Accepted, MailError, Message

log = logging.getLogger(__name__)

_ENV = "CLANNON_ENV"
_MAILER_ENV = "CLANNON_MAILER"
_RESEND_KEY_ENV = "RESEND_API_KEY"
_SENDER_ENV = "CLANNON_MAIL_FROM"


class LogMailer:
    """Accepts every message and sends nothing. Dev only, and says so."""

    def __init__(self) -> None:
        self.sent: list[Message] = []   # inspectable in tests; bounded by process life

    async def send(self, message: Message) -> Accepted:
        self.sent.append(message)
        log.warning(
            "MAIL NOT SENT (LogMailer active — no provider configured): to=%s subject=%r",
            message.to, message.subject,
        )
        # The body carries a one-time verification link. Logging it is what makes local
        # development possible at all, and is also exactly why this class refuses to
        # start in production — see resolve_mailer.
        log.info("mail body to %s:\n%s", message.to, message.text)
        return Accepted(provider_id=None)


class ResendMailer:
    """Resend (https://resend.com) — the production transport.

    Chosen over SES for one blocking reason, not a preference: **SES starts every new
    account in a sandbox that can only send to pre-verified addresses.** A waitlist
    exists precisely to mail strangers, so SES cannot run it at all until AWS grants
    production access through a support ticket — a human-in-the-loop dependency that
    can take days and can be refused. Resend needs DNS records and nothing else.

    It also costs no new dependency: this is one POST with a bearer token, so `httpx`
    (already here) is enough. SES would mean boto3 for a single call, or hand-rolled
    SigV4 signing.

    SES wins on price far above alpha volume ($0.10/1000 vs a free tier of 3,000/month).
    If that day comes, this class is the only thing that changes.
    """

    _ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str, *, timeout_s: float = 10.0) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout_s = timeout_s

    async def send(self, message: Message) -> Accepted:
        payload = {
            "from": self._sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            payload["html"] = message.html
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(
                    self._ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            # Typed at the boundary so callers never catch an httpx class and quietly
            # couple themselves to the library this module exists to isolate.
            raise MailError(f"mail transport failed: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            # Body may echo the recipient; status and a short reason only. Never the
            # key, never the address (LAW 5 — no secrets or user data in logs).
            raise MailError(f"mail provider rejected the message (HTTP {response.status_code})")

        provider_id = None
        try:
            provider_id = (response.json() or {}).get("id")
        except ValueError:
            pass  # accepted but unparseable body — still accepted, id simply unknown
        return Accepted(provider_id=provider_id)


def resolve_mailer() -> LogMailer | ResendMailer:
    """The single place a mailer is chosen.

    Fails closed in production rather than degrading to a no-op: an alpha whose
    verification mail goes to a log file is one nobody can join, and it would look
    identical to a working system from the server's side.
    """
    env = (os.getenv(_ENV) or "dev").strip().lower()
    configured = (os.getenv(_MAILER_ENV) or "log").strip().lower()

    if configured == "log":
        if env in {"prod", "production"}:
            raise MailError(
                "no email provider configured (CLANNON_MAILER=log) and CLANNON_ENV is "
                "production — refusing to start with a mailer that sends nothing"
            )
        return LogMailer()

    if configured == "resend":
        api_key = (os.getenv(_RESEND_KEY_ENV) or "").strip()
        sender = (os.getenv(_SENDER_ENV) or "").strip()
        # Fail at resolve time, not at the first signup: a missing key must not become
        # a runtime surprise for the first stranger who tries to join.
        if not api_key:
            raise MailError(f"CLANNON_MAILER=resend but {_RESEND_KEY_ENV} is not set")
        if not sender:
            raise MailError(
                f"CLANNON_MAILER=resend but {_SENDER_ENV} is not set "
                "(e.g. 'Clannon <hello@yourdomain.com>' — the domain must be verified "
                "in Resend with its SPF/DKIM DNS records, or mail will not arrive)"
            )
        return ResendMailer(api_key, sender)

    raise MailError(
        f"unknown mailer {configured!r} (set CLANNON_MAILER=log for dev, or resend)"
    )
