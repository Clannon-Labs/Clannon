"""Owner-only CLI: list and approve private-alpha waitlist entries.

Not an HTTP route (see `waitlist.py`'s module docstring for why) — there is exactly
one owner, so a local script IS the whole privilege boundary; an authenticated HTTP
surface here would be a new one to secure for no benefit over shell access.

    .venv/bin/python -m api.waitlist_cli list
    .venv/bin/python -m api.waitlist_cli approve <email>

`approve` is idempotent-ish and safe to re-run: it always (re-)issues a fresh
approval token and (re-)sends the invite, so a lost or expired link is fixed by
running it again.
"""

from __future__ import annotations

import asyncio
import sys

from foundation import MailError
from settings import WAITLIST

from . import waitlist_store
from .waitlist import approval_message
from core.mail import resolve_mailer


async def _approve(email: str) -> None:
    email = email.strip().lower()
    entry = waitlist_store.waitlist_get(email)
    if entry is None or not entry["email_verified"]:
        print(f"{email}: not on the waitlist, or not yet email-verified — nothing to approve.")
        return
    waitlist_store.waitlist_mark_approved(email)
    token = waitlist_store.waitlist_issue_token(email, "approval", WAITLIST.approval_token_ttl_hours * 3600)
    try:
        await resolve_mailer().send(approval_message(email, token))
    except MailError as exc:
        print(f"{email}: approved, but the invite email failed to send ({exc}). Re-run to retry.")
        return
    print(f"{email}: approved. Invite sent (expires in {WAITLIST.approval_token_ttl_hours}h).")


def _list_pending() -> None:
    pending = waitlist_store.waitlist_list_pending()
    if not pending:
        print("No verified, unapproved waitlist entries.")
        return
    for entry in pending:
        note = f" — {entry['note']}" if entry.get("note") else ""
        print(f"{entry['email']}{note}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"list", "approve"}:
        print(__doc__)
        raise SystemExit(1)
    if sys.argv[1] == "list":
        _list_pending()
        return
    if len(sys.argv) < 3:
        print("usage: python -m api.waitlist_cli approve <email>")
        raise SystemExit(1)
    asyncio.run(_approve(sys.argv[2]))


if __name__ == "__main__":
    main()
