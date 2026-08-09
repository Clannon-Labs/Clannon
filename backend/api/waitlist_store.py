"""SQLite persistence for the private-alpha waitlist (owner ruling 2026-08-09).

Split out of `auth.py` to keep that file under LAW 2's length bound — same pattern
as `run_persistence.py`/`run_store.py`: this module reaches into `auth._db()` for
the shared connection/schema exactly like `run_store.py` already does, so there is
still ONE connection factory and ONE migration path, just not one file.

Caps/TTLs are read from `settings.WAITLIST` by the CALLER (`waitlist.py`,
`waitlist_cli.py`) and passed in here — this module stays config-agnostic like the
rest of the data layer.
"""

from __future__ import annotations

import secrets
import time

from . import auth


def email_registered(email: str) -> bool:
    """True if `email` already belongs to a real account (waitlisting it is a no-op)."""
    with auth._db() as db:
        row = db.execute(
            "SELECT 1 FROM users WHERE email=?", (email.strip().lower(),)
        ).fetchone()
    return row is not None


def waitlist_get(email: str) -> dict | None:
    with auth._db() as db:
        row = db.execute(
            "SELECT * FROM waitlist WHERE email=?", (email.strip().lower(),)
        ).fetchone()
    return dict(row) if row is not None else None


def waitlist_upsert(email: str, note: str | None) -> None:
    """Insert a waitlist entry if this email isn't already listed. An existing entry is
    left untouched — a repeat submission never resets verification/approval state, and
    never overwrites the original note."""
    with auth._db() as db:
        db.execute(
            "INSERT OR IGNORE INTO waitlist (email,note,created_at) VALUES (?,?,?)",
            (email.strip().lower(), note, time.time()),
        )


def waitlist_verify_send_allowed(email: str, max_sends: int, cooldown_s: int) -> bool:
    """Whether a verification email may be sent now — caps total sends per address
    (independent of the per-caller IP rate limit, which someone cycling addresses
    would sail past) and enforces a cooldown between sends."""
    with auth._db() as db:
        row = db.execute(
            "SELECT verify_send_count, last_verify_sent_at FROM waitlist WHERE email=?",
            (email.strip().lower(),),
        ).fetchone()
    if row is None:
        return True
    if row["verify_send_count"] >= max_sends:
        return False
    last = row["last_verify_sent_at"]
    return last is None or time.time() - last >= cooldown_s


def waitlist_record_verify_sent(email: str) -> None:
    """Count a verification send against the cap. Call ONLY after the mailer accepted
    the message — a failed send must not burn the caller's resend budget."""
    with auth._db() as db:
        db.execute(
            "UPDATE waitlist SET verify_send_count = verify_send_count + 1, "
            "last_verify_sent_at=? WHERE email=?",
            (time.time(), email.strip().lower()),
        )


def waitlist_mark_verified(email: str) -> None:
    with auth._db() as db:
        db.execute(
            "UPDATE waitlist SET email_verified=1, verified_at=? WHERE email=?",
            (time.time(), email.strip().lower()),
        )


def waitlist_mark_approved(email: str) -> bool:
    """Owner-only (CLI). True if a verified entry existed and was (re-)approved —
    re-approving an already-approved entry is allowed, so the owner can reissue an
    invite whose link has expired or whose mail failed to send."""
    email = email.strip().lower()
    with auth._db() as db:
        updated = db.execute(
            "UPDATE waitlist SET approved=1, approved_at=? WHERE email=? AND email_verified=1",
            (time.time(), email),
        ).rowcount
    return bool(updated)


def waitlist_list_pending() -> list[dict]:
    """Verified-but-unapproved entries, oldest first — what the owner's CLI shows."""
    with auth._db() as db:
        rows = db.execute(
            "SELECT * FROM waitlist WHERE email_verified=1 AND approved=0 "
            "ORDER BY verified_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def waitlist_issue_token(email: str, kind: str, ttl_seconds: int) -> str:
    """Mint one unguessable, single-use token of `kind` ('verify' | 'approval') for
    `email`; only its SHA-256 hash is stored, matching session-token handling."""
    token = secrets.token_urlsafe(32)
    with auth._db() as db:
        db.execute(
            "INSERT INTO waitlist_tokens (token_hash,email,kind,expires_at,created_at) "
            "VALUES (?,?,?,?,?)",
            (auth._hash_token(token), email.strip().lower(), kind, time.time() + ttl_seconds, time.time()),
        )
    return token


def waitlist_consume_token(token: str, kind: str) -> str | None:
    """Atomically claim a token: unknown, wrong-kind, expired, and already-consumed all
    return None identically (obligation: indistinguishable). The guarded UPDATE is the
    single point of consumption — a second concurrent caller sees rowcount 0."""
    now = time.time()
    token_hash = auth._hash_token(token)
    with auth._db() as db:
        updated = db.execute(
            """UPDATE waitlist_tokens SET consumed_at=?
               WHERE token_hash=? AND kind=? AND expires_at>? AND consumed_at IS NULL""",
            (now, token_hash, kind, now),
        ).rowcount
        if not updated:
            return None
        row = db.execute(
            "SELECT email FROM waitlist_tokens WHERE token_hash=?", (token_hash,)
        ).fetchone()
    return row["email"] if row is not None else None
