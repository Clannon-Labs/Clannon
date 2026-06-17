"""
Cookie-session auth with a SQLite store.

This is the development stand-in for the planned Supabase auth: real
password hashing (scrypt), real httpOnly sessions, real per-user scoping —
so the frontend integrates against production-shaped behavior. When
Supabase lands, this module is the only thing that changes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response

from . import config

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            pw_hash BLOB NOT NULL, pw_salt BLOB NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS wiki_entries (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            content TEXT NOT NULL, updated_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            brief TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0, log_json TEXT NOT NULL DEFAULT '[]',
            experts_json TEXT NOT NULL DEFAULT '[]', report TEXT, message TEXT,
            memory_writes_json TEXT NOT NULL DEFAULT '[]',
            feedback_rating TEXT, feedback_comment TEXT, feedback_at REAL,
            parent_run_id TEXT, session_id TEXT, block_stage TEXT,
            artifacts_json TEXT NOT NULL DEFAULT '[]',
            inputs_json TEXT NOT NULL DEFAULT '[]'
        )"""
    )
    # self-healing migration: add columns missing on databases created before
    # the feedback/follow-up feature (CREATE TABLE IF NOT EXISTS won't alter them)
    _existing = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    for _col, _decl in (
        ("feedback_rating", "TEXT"),
        ("feedback_comment", "TEXT"),
        ("feedback_at", "REAL"),
        ("parent_run_id", "TEXT"),
        ("session_id", "TEXT"),
        ("block_stage", "TEXT"),
        ("artifacts_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("inputs_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("message", "TEXT"),
    ):
        if _col not in _existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {_col} {_decl}")
    # backfill: pre-session rows become their own single-turn session
    conn.execute("UPDATE runs SET session_id = id WHERE session_id IS NULL OR session_id = ''")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS model_prefs (
            user_id TEXT NOT NULL, layer TEXT NOT NULL, model TEXT NOT NULL,
            PRIMARY KEY (user_id, layer)
        )"""
    )
    return conn


@dataclass
class User:
    id: str
    email: str
    name: str
    plan: str

    def as_json(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name, "plan": self.plan}


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(email: str, name: str, password: str) -> User:
    email = email.strip().lower()
    if len(password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters.")
    salt = secrets.token_bytes(16)
    with _db() as db:
        if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists.")
        uid = f"u_{secrets.token_hex(8)}"
        db.execute(
            "INSERT INTO users (id,email,name,pw_hash,pw_salt,plan,created_at) VALUES (?,?,?,?,?,?,?)",
            (uid, email, name.strip(), _hash_password(password, salt), salt, config.DEFAULT_PLAN, time.time()),
        )
    return User(uid, email, name.strip(), config.DEFAULT_PLAN)


def verify_user(email: str, password: str) -> User:
    email = email.strip().lower()
    with _db() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    # constant-time compare; same error whether email or password is wrong
    if row is None or not hmac.compare_digest(
        _hash_password(password, row["pw_salt"]), row["pw_hash"]
    ):
        raise HTTPException(401, "Invalid email or password.")
    return User(row["id"], row["email"], row["name"], row["plan"])


def start_session(response: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    with _db() as db:
        db.execute(
            "INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
            (_hash_token(token), user.id, time.time() + config.SESSION_TTL_S),
        )
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    response.set_cookie(
        config.COOKIE_NAME,
        token,
        max_age=config.SESSION_TTL_S,
        httponly=True,
        samesite="lax",   # apex ↔ subdomain are the same site, so Lax carries the cookie on top-level nav
        secure=config.COOKIE_SECURE,
        domain=config.COOKIE_DOMAIN,   # None = host-only (dev); ".clannon.com" = shared apex + subdomains
        path="/",
    )


def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(config.COOKIE_NAME)
    if token:
        with _db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
    response.delete_cookie(config.COOKIE_NAME, path="/", domain=config.COOKIE_DOMAIN)


def current_user(request: Request) -> User:
    token = request.cookies.get(config.COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Not signed in.")
    with _db() as db:
        row = db.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash=? AND s.expires_at > ?""",
            (_hash_token(token), time.time()),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "Session expired.")
    return User(row["id"], row["email"], row["name"], row["plan"])


def fetch_wiki(user_id: str) -> list[dict]:
    """A user's wiki entries (title + content), newest first. Handed to the
    pipeline so the memory manager can load the wiki tier as text at hydration."""
    with _db() as db:
        rows = db.execute(
            "SELECT title, content FROM wiki_entries WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [{"title": r["title"], "content": r["content"]} for r in rows]


# ---------------------------------------------------------------------------
# Data access — all persistence lives in this module (the one swapped for
# Supabase). Routes/handlers call these typed functions; they never open the DB
# or write SQL themselves. Functions return plain dicts of raw columns; the API
# layer owns presentation (camelCase keys, ISO timestamps).
# ---------------------------------------------------------------------------

def _wiki_row(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "title": row["title"], "content": row["content"], "updated_at": row["updated_at"]}


def wiki_list(user_id: str) -> list[dict]:
    """All of a user's wiki entries, newest first (raw columns)."""
    with _db() as db:
        rows = db.execute(
            "SELECT * FROM wiki_entries WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
        ).fetchall()
    return [_wiki_row(r) for r in rows]


def wiki_create(user_id: str, title: str, content: str) -> dict:
    """Insert one wiki entry and return it."""
    entry_id = f"m_{secrets.token_hex(6)}"
    with _db() as db:
        db.execute(
            "INSERT INTO wiki_entries (id,user_id,title,content,updated_at) VALUES (?,?,?,?,?)",
            (entry_id, user_id, title, content, time.time()),
        )
        row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
    return _wiki_row(row)


def wiki_update(user_id: str, entry_id: str, title: str, content: str) -> dict | None:
    """Update one of the user's wiki entries; None if it does not exist / not theirs."""
    with _db() as db:
        updated = db.execute(
            "UPDATE wiki_entries SET title=?, content=?, updated_at=? WHERE id=? AND user_id=?",
            (title, content, time.time(), entry_id, user_id),
        ).rowcount
        if not updated:
            return None
        row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
    return _wiki_row(row)


def wiki_delete(user_id: str, entry_id: str) -> bool:
    """Delete one of the user's wiki entries; False if it did not exist."""
    with _db() as db:
        deleted = db.execute(
            "DELETE FROM wiki_entries WHERE id=? AND user_id=?", (entry_id, user_id)
        ).rowcount
    return bool(deleted)


def wiki_bulk_create(user_id: str, entries: list[tuple[str, str]]) -> list[dict]:
    """Insert several wiki entries (title, content) in one transaction; return them."""
    created: list[dict] = []
    with _db() as db:
        for title, content in entries:
            entry_id = f"m_{secrets.token_hex(6)}"
            db.execute(
                "INSERT INTO wiki_entries (id,user_id,title,content,updated_at) VALUES (?,?,?,?,?)",
                (entry_id, user_id, title, content, time.time()),
            )
            row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
            created.append(_wiki_row(row))
    return created


def model_prefs_get(user_id: str) -> dict[str, str]:
    """A user's saved per-role model choices, as {layer: model}."""
    with _db() as db:
        return {
            row["layer"]: row["model"]
            for row in db.execute(
                "SELECT layer, model FROM model_prefs WHERE user_id=?", (user_id,)
            )
        }


def model_prefs_set(user_id: str, layer: str, model: str) -> None:
    """Upsert a user's workspace default model for one role."""
    with _db() as db:
        db.execute(
            "INSERT INTO model_prefs (user_id, layer, model) VALUES (?,?,?) "
            "ON CONFLICT(user_id, layer) DO UPDATE SET model=excluded.model",
            (user_id, layer, model),
        )
