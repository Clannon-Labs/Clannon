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
            content TEXT NOT NULL, updated_at REAL NOT NULL, project_id TEXT
        )"""
    )
    # A project = a client or body of work; its runs + memory are scoped to it.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            color TEXT, created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            brief TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            log_json TEXT NOT NULL DEFAULT '[]',
            experts_json TEXT NOT NULL DEFAULT '[]', report TEXT, message TEXT,
            memory_writes_json TEXT NOT NULL DEFAULT '[]',
            feedback_rating TEXT, feedback_comment TEXT, feedback_at REAL,
            parent_run_id TEXT, session_id TEXT, lineage_prefix_json TEXT, block_stage TEXT,
            artifacts_json TEXT NOT NULL DEFAULT '[]',
            inputs_json TEXT NOT NULL DEFAULT '[]', project_id TEXT,
            sources_json TEXT NOT NULL DEFAULT '[]', verification_state TEXT,
            completion_state TEXT NOT NULL DEFAULT 'complete', completion_reason TEXT,
            superseded INTEGER NOT NULL DEFAULT 0
        )"""
    )
    # Self-healing additive migrations: CREATE TABLE IF NOT EXISTS does not alter
    # databases created before a field shipped.
    _existing = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    for _col, _decl in (
        ("feedback_rating", "TEXT"),
        ("feedback_comment", "TEXT"),
        ("feedback_at", "REAL"),
        ("cache_read_tokens", "INTEGER NOT NULL DEFAULT 0"),
        ("cache_write_tokens", "INTEGER NOT NULL DEFAULT 0"),
        ("parent_run_id", "TEXT"),
        ("session_id", "TEXT"),
        ("lineage_prefix_json", "TEXT"),
        ("block_stage", "TEXT"),
        ("artifacts_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("inputs_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("message", "TEXT"),
        ("project_id", "TEXT"),
        ("sources_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("verification_state", "TEXT"),
        # rows written before honest-completion landed were all runs that reached a
        # terminal status without a degraded marker, so `complete` is the truthful
        # backfill — not merely the convenient default.
        ("completion_state", "TEXT NOT NULL DEFAULT 'complete'"),
        ("completion_reason", "TEXT"),
        ("superseded", "INTEGER NOT NULL DEFAULT 0"),
        ("started_at", "TEXT"),
        ("first_message_at", "TEXT"),
        ("completed_at", "TEXT"),
    ):
        if _col not in _existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {_col} {_decl}")
    if "project_id" not in {r[1] for r in conn.execute("PRAGMA table_info(wiki_entries)")}:
        conn.execute("ALTER TABLE wiki_entries ADD COLUMN project_id TEXT")
    # backfill: pre-session rows become their own single-turn session
    conn.execute("UPDATE runs SET session_id = id WHERE session_id IS NULL OR session_id = ''")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS model_prefs (
            user_id TEXT NOT NULL, layer TEXT NOT NULL, model TEXT NOT NULL,
            PRIMARY KEY (user_id, layer)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS security_audit (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            block_code TEXT NOT NULL,
            threat_level TEXT NOT NULL,
            origin TEXT NOT NULL,
            reason TEXT,
            blocked_at REAL NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS security_audit_by_run "
        "ON security_audit (user_id, trace_id)"
    )
    # CB4 institutional decision memory: a durable mirror of the live decision log's
    # DERIVED records (core.orchestrator.utils.decision_log.derive_record), written
    # once per terminal run, user_id-scoped. One row per decision point (tool_call /
    # answer kinds only, per derive_record's own filter) — not a raw log dump.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS decision_records (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            kind TEXT NOT NULL,
            decision TEXT NOT NULL,
            reasoning TEXT NOT NULL DEFAULT '',
            participants_json TEXT NOT NULL DEFAULT '[]',
            decided_at REAL NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS decision_records_by_run "
        "ON decision_records (user_id, trace_id)"
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


def user_plan(user_id: str) -> str | None:
    """Current server-side plan for one trusted user id; None when absent."""
    with _db() as db:
        row = db.execute("SELECT plan FROM users WHERE id=?", (user_id,)).fetchone()
    return row["plan"] if row is not None else None


def fetch_wiki(user_id: str, project_id: str | None = None) -> list[dict]:
    """A user's wiki entries (title + content), newest first. Handed to the
    pipeline so the memory manager can load the wiki tier as text at hydration.
    Scoped to one project when `project_id` is given (a project's runs only see that
    project's wiki); the whole account's wiki when it is None (a run with no project)."""
    sql = "SELECT title, content FROM wiki_entries WHERE user_id=?"
    params: tuple = (user_id,)
    if project_id is not None:
        sql += " AND project_id=?"
        params += (project_id,)
    sql += " ORDER BY updated_at DESC"
    with _db() as db:
        rows = db.execute(sql, params).fetchall()
    return [{"title": r["title"], "content": r["content"]} for r in rows]


# ---------------------------------------------------------------------------
# Data access — all persistence lives in this module (the one swapped for
# Supabase). Routes/handlers call these typed functions; they never open the DB
# or write SQL themselves. Functions return plain dicts of raw columns; the API
# layer owns presentation (camelCase keys, ISO timestamps).
# ---------------------------------------------------------------------------

def _wiki_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "title": row["title"], "content": row["content"],
        "updated_at": row["updated_at"],
        "project_id": (row["project_id"] if "project_id" in row.keys() else None),
    }


def wiki_list(user_id: str, project_id: str | None = None) -> list[dict]:
    """A user's wiki entries, newest first (raw columns). Scoped to one project when
    `project_id` is given; the whole account when None."""
    sql = "SELECT * FROM wiki_entries WHERE user_id=?"
    params: tuple = (user_id,)
    if project_id is not None:
        sql += " AND project_id=?"
        params += (project_id,)
    sql += " ORDER BY updated_at DESC"
    with _db() as db:
        rows = db.execute(sql, params).fetchall()
    return [_wiki_row(r) for r in rows]


def wiki_get(user_id: str, entry_id: str) -> dict | None:
    """One owner-scoped wiki entry; foreign and unknown ids are identical."""
    with _db() as db:
        row = db.execute(
            "SELECT * FROM wiki_entries WHERE id=? AND user_id=?",
            (entry_id, user_id),
        ).fetchone()
    return _wiki_row(row) if row is not None else None


def wiki_create(user_id: str, title: str, content: str, project_id: str | None = None) -> dict:
    """Insert one wiki entry (optionally scoped to a project) and return it."""
    entry_id = f"m_{secrets.token_hex(6)}"
    with _db() as db:
        db.execute(
            "INSERT INTO wiki_entries (id,user_id,title,content,updated_at,project_id) VALUES (?,?,?,?,?,?)",
            (entry_id, user_id, title, content, time.time(), project_id),
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


def wiki_bulk_create(user_id: str, entries: list[tuple[str, str]], project_id: str | None = None) -> list[dict]:
    """Insert several wiki entries (title, content) in one transaction (optionally scoped
    to a project); return them."""
    created: list[dict] = []
    with _db() as db:
        for title, content in entries:
            entry_id = f"m_{secrets.token_hex(6)}"
            db.execute(
                "INSERT INTO wiki_entries (id,user_id,title,content,updated_at,project_id) VALUES (?,?,?,?,?,?)",
                (entry_id, user_id, title, content, time.time(), project_id),
            )
            row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
            created.append(_wiki_row(row))
    return created


# ---------------------------------------------------------------------------
# Projects — a project = a client or body of work; runs + memory scope to it.
# ---------------------------------------------------------------------------

def _project_row(row: sqlite3.Row) -> dict:
    keys = row.keys()
    return {
        "id": row["id"], "name": row["name"],
        "color": (row["color"] if "color" in keys else None),
        "created_at": row["created_at"],
        "last_activity": (row["last_activity"] if "last_activity" in keys else None),
    }


def project_list(user_id: str) -> list[dict]:
    """A user's projects, **newest activity first** — ordered by the most recent run in
    each project, then by creation time for projects with no runs yet."""
    with _db() as db:
        rows = db.execute(
            """SELECT p.*, MAX(r.created_at) AS last_activity
               FROM projects p
               LEFT JOIN runs r ON r.project_id = p.id AND r.user_id = p.user_id
                   AND r.superseded = 0
               WHERE p.user_id = ?
               GROUP BY p.id
               ORDER BY (last_activity IS NULL), last_activity DESC, p.created_at DESC""",
            (user_id,),
        ).fetchall()
    return [_project_row(r) for r in rows]


def project_get(user_id: str, project_id: str) -> dict | None:
    """One project, scoped to its owner (the ownership check for any projectId a request
    carries — NEVER trust a projectId without it). None if it isn't this user's."""
    with _db() as db:
        row = db.execute(
            "SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, user_id)
        ).fetchone()
    return _project_row(row) if row else None


def project_create(user_id: str, name: str, color: str | None = None) -> dict:
    """Insert one project and return it."""
    pid = f"proj_{secrets.token_hex(6)}"
    with _db() as db:
        db.execute(
            "INSERT INTO projects (id,user_id,name,color,created_at) VALUES (?,?,?,?,?)",
            (pid, user_id, name, color, time.time()),
        )
        row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return _project_row(row)


def project_rename(user_id: str, project_id: str, name: str) -> dict | None:
    """Rename one of the user's projects; None if it does not exist / not theirs."""
    with _db() as db:
        updated = db.execute(
            "UPDATE projects SET name=? WHERE id=? AND user_id=?", (name, project_id, user_id)
        ).rowcount
        if not updated:
            return None
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return _project_row(row)


def project_delete_row(user_id: str, project_id: str) -> None:
    """Delete a project row AND its wiki entries, scoped to the owner. The cascade of its
    RUNS (live tasks + persisted rows + stored files) is run_store's job — it calls this
    after evicting them. Best-effort/idempotent: deleting nothing is fine."""
    with _db() as db:
        db.execute("DELETE FROM wiki_entries WHERE user_id=? AND project_id=?", (user_id, project_id))
        db.execute("DELETE FROM projects WHERE id=? AND user_id=?", (project_id, user_id))


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
