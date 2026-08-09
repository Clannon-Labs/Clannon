"""HTTP contract for the private-alpha waitlist (owner ruling 2026-08-09).

`settings.WAITLIST.enabled` is the single switch: while true, `POST /auth/signup`
(in `app.py`) refuses without a valid approval token and this router is the only
way in — join, verify the inbox, wait for the owner. Owner approval itself is a
CLI (`waitlist_cli.py`), not a route: there is exactly one owner, so an HTTP
surface for it would be a new privilege boundary to secure for no benefit over
shell access to this machine.

Every route here is public, so every route rate-limits and none may disclose
whether an address is already listed/verified/approved (that would make this an
account-existence oracle) — see `join_waitlist` and `resend_verification`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from fastapi.responses import RedirectResponse

from foundation import MailError, Message
from settings import WAITLIST

from . import config, waitlist_store
from core.mail import resolve_mailer

log = logging.getLogger(__name__)

router = APIRouter()

# Every /waitlist* response that must not leak list membership converges on this body.
_ACCEPTED = {"status": "ok"}


def _rate_limit(request: Request) -> None:
    """Reuses api.app's shared per-IP limiter (one limiter, not one per module).
    Imported lazily: app.py is still assembling its router table when this module
    first loads, and `tests/conftest.py` resets the single dict at `api.app._auth_attempts`
    — importing eagerly would risk a second, unreset copy."""
    from . import app as _app

    _app._auth_rate_limit(request)


def _verify_url(token: str) -> str:
    return f"{config.FRONTEND_ORIGIN}/waitlist/verify?token={token}"


def _activate_url(token: str) -> str:
    return f"{config.FRONTEND_ORIGIN}/signup?approvalToken={token}"


def verify_message(email: str, token: str) -> Message:
    return Message(
        to=email,
        subject="Confirm your email — Clannon waitlist",
        text=(
            "Confirm this address to join the Clannon private alpha waitlist:\n\n"
            f"{_verify_url(token)}\n\n"
            f"This link expires in {WAITLIST.verify_token_ttl_hours} hours. "
            "If you didn't request this, ignore this email."
        ),
    )


def approval_message(email: str, token: str) -> Message:
    return Message(
        to=email,
        subject="You're in — set up your Clannon account",
        text=(
            "You've been approved for the Clannon private alpha.\n\n"
            f"Create your account: {_activate_url(token)}\n\n"
            f"This link expires in {WAITLIST.approval_token_ttl_hours} hours."
        ),
    )


async def _send_verify_email(email: str) -> None:
    """Issue a verify token and mail it. The waitlist entry is already written before
    this runs, so a mail failure never creates a half-state — worst case, the address
    sits unverified until a `/waitlist/resend` succeeds. A failed send does NOT count
    against the resend cap; only an accepted one does."""
    token = waitlist_store.waitlist_issue_token(email, "verify", WAITLIST.verify_token_ttl_hours * 3600)
    try:
        await resolve_mailer().send(verify_message(email, token))
    except MailError:
        log.warning("waitlist verify mail failed for an address; caller may retry via /waitlist/resend")
        return
    waitlist_store.waitlist_record_verify_sent(email)


class JoinBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    note: str | None = Field(default=None, max_length=WAITLIST.note_max_chars)


class ResendBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


@router.post("/waitlist", status_code=202)
async def join_waitlist(body: JoinBody, request: Request) -> dict:
    """Join the waitlist. Always returns the same body regardless of whether the
    address is new, already listed, already verified, or already a real account —
    this endpoint is public and would otherwise be an account-existence oracle."""
    _rate_limit(request)
    email = body.email.strip().lower()
    note = (body.note or "").strip() or None
    if not waitlist_store.email_registered(email):
        waitlist_store.waitlist_upsert(email, note)
        entry = waitlist_store.waitlist_get(email)
        if (
            entry is not None
            and not entry["email_verified"]
            and waitlist_store.waitlist_verify_send_allowed(
                email, WAITLIST.max_verification_sends_per_email, WAITLIST.resend_cooldown_seconds
            )
        ):
            await _send_verify_email(email)
    return _ACCEPTED


@router.post("/waitlist/resend", status_code=202)
async def resend_verification(body: ResendBody, request: Request) -> dict:
    """Resend the verification email. Same non-disclosure as `join_waitlist`: an
    unknown address, an already-verified one, and one over its send cap all return
    the identical body."""
    _rate_limit(request)
    email = body.email.strip().lower()
    entry = waitlist_store.waitlist_get(email)
    if (
        entry is not None
        and not entry["email_verified"]
        and waitlist_store.waitlist_verify_send_allowed(
            email, WAITLIST.max_verification_sends_per_email, WAITLIST.resend_cooldown_seconds
        )
    ):
        await _send_verify_email(email)
    return _ACCEPTED


@router.get("/waitlist/verify")
async def verify_waitlist(
    request: Request, token: str = Query(..., min_length=1, max_length=256)
) -> RedirectResponse:
    """Consume a one-time verification token. Only the caller's OWN link outcome is
    visible here (redirect target) — that is not an address oracle, since the token
    is unguessable and never disclosed to anyone but the recipient."""
    _rate_limit(request)
    email = waitlist_store.waitlist_consume_token(token, "verify")
    if email is not None:
        waitlist_store.waitlist_mark_verified(email)
        return RedirectResponse(f"{config.FRONTEND_ORIGIN}/waitlist/confirmed")
    return RedirectResponse(f"{config.FRONTEND_ORIGIN}/waitlist/invalid-link")
