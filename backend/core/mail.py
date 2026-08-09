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

from foundation import Accepted, MailError, Message

log = logging.getLogger(__name__)

_ENV = "CLANNON_ENV"
_MAILER_ENV = "CLANNON_MAILER"


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


def resolve_mailer() -> LogMailer:
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

    raise MailError(f"unknown mailer {configured!r} (set CLANNON_MAILER=log for dev)")
