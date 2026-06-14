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
            experts_json TEXT NOT NULL DEFAULT '[]', report TEXT,
            memory_writes_json TEXT NOT NULL DEFAULT '[]',
            feedback_rating TEXT, feedback_comment TEXT, feedback_at REAL,
            parent_run_id TEXT, session_id TEXT, block_stage TEXT,
            artifacts_json TEXT NOT NULL DEFAULT '[]'
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
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(config.COOKIE_NAME)
    if token:
        with _db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
    response.delete_cookie(config.COOKIE_NAME, path="/")


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
