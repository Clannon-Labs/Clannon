"""
Mailer — the contract for sending transactional email.

Clannon had no way to send mail at all before this (verified 2026-08-09: no smtp,
sendgrid, resend, postmark, mailgun or ses anywhere; `pydantic[email]` only validates
address syntax). The waitlist flow needs one, so the dependency arrives behind a single
door rather than as a provider SDK sprinkled through `api/` — LAW 6.

Three things this contract deliberately does NOT do, each for a reason:

- **No templating.** A port that renders is a port that owns copy, and copy belongs in
  `config/`. Callers pass finished subject and body.
- **No retry, no queue.** Those are the transport's concern and differ per provider.
  A caller that needs durability must not infer it from a bare `send()` returning.
- **No "was it delivered?"** Nobody can answer that synchronously. `send()` returning
  means the provider accepted the message, and the type name says exactly that.

The last one matters most. A verification email that is accepted and then bounces is
indistinguishable, from here, from one that arrives — so the waitlist must never render
"check your inbox" as proof of anything, and must offer a resend path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class MailError(Exception):
    """The transport refused or failed to accept the message.

    Typed so callers can fail closed on it rather than swallowing a provider's
    exception class, which would couple them to the provider we are isolating.
    """


@dataclass(frozen=True, slots=True)
class Message:
    """One outbound email. Body is plain text; `html` is optional and additive."""

    to: str
    subject: str
    text: str
    html: str | None = None


@dataclass(frozen=True, slots=True)
class Accepted:
    """The provider took responsibility for the message. NOT proof of delivery."""

    provider_id: str | None  # provider's message id, when it gives one


@runtime_checkable
class Mailer(Protocol):
    """Send transactional email. One door; implementations live behind it."""

    async def send(self, message: Message) -> Accepted:
        """Hand `message` to the transport.

        Raises `MailError` if the transport refused it. Returning means accepted for
        delivery and nothing stronger.
        """
        ...
