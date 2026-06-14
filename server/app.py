"""
The FastAPI application — serves the contract in clannon/frontend/README.md.

    .venv/bin/uvicorn server.app:app --port 8000

Set FRONTEND_ORIGIN for CORS (default http://localhost:3000). Loads .env /
.env.local exactly like main.py so the pipeline gets its provider keys.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from dotenv import load_dotenv

# Same env bootstrap as main.py — before anything builds provider clients.
load_dotenv(".env")
load_dotenv(".env.local", override=True)

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from core.artifacts import LocalArtifactStore
from security.sanitizers import uploads as upload_scan

from . import auth, config, runs

app = FastAPI(title="Clannon API (Vraksha engine)", version=config.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- public config (read-only sync) ----------


@app.get("/config")
def get_config() -> dict:
    return config.remote_config()


# ---------- auth ----------

# Sliding-window rate limit on credential endpoints (per client IP):
# blunts brute-force and signup flooding. In-memory is fine per-process;
# Redis takes over when the cloud deployment lands.
_AUTH_WINDOW_S = 60
_AUTH_MAX_ATTEMPTS = 10
_auth_attempts: dict[str, list[float]] = {}


def _auth_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    recent = [t for t in _auth_attempts.get(ip, []) if now - t < _AUTH_WINDOW_S]
    if len(recent) >= _AUTH_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts — wait a minute and try again.")
    recent.append(now)
    _auth_attempts[ip] = recent


class SignupBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/signup")
def signup(body: SignupBody, request: Request, response: Response) -> dict:
    _auth_rate_limit(request)
    user = auth.create_user(body.email, body.name, body.password)
    auth.start_session(response, user)
    return user.as_json()


@app.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    _auth_rate_limit(request)
    user = auth.verify_user(body.email, body.password)
    auth.start_session(response, user)
    return user.as_json()


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    auth.end_session(request, response)
    response.status_code = 204
    return response


@app.get("/auth/me")
def me(user: auth.User = Depends(auth.current_user)) -> dict:
    return user.as_json()


@app.get("/auth/oauth/{provider}")
def oauth_start(provider: str) -> RedirectResponse:
    # Supabase OAuth replaces this. Until then, send the user back to the
    # sign-in page with a readable error instead of stranding them on JSON.
    return RedirectResponse(f"{config.FRONTEND_ORIGIN}/login?error=oauth_unavailable")


# ---------- runs ----------


# Run creation is multipart so a brief can carry optional input files (a CSV to
# analyze, code to work on). Files are malware-scanned at this boundary and the
# clean originals are seeded into the expert workspace; the brief still crosses
# the full pipeline.
_MAX_INPUT_FILES = 10


async def _admit_uploads(files: list[UploadFile]) -> list:
    """Scan each uploaded file at the boundary; return the admitted InputFiles.
    A rejected file (oversized, unsupported, malicious, unscannable) is a 422 with
    a readable reason — the run is never created with an unscanned file."""
    if not files:
        return []
    if len(files) > _MAX_INPUT_FILES:
        raise HTTPException(422, f"At most {_MAX_INPUT_FILES} files per run.")
    admitted = []
    for upload in files:
        data = await upload.read()
        item, reason = await upload_scan.scan_upload(upload.filename or "upload", data)
        if reason:
            raise HTTPException(422, reason)
        admitted.append(item)
    return admitted


@app.get("/runs")
def list_runs(user: auth.User = Depends(auth.current_user)) -> list[dict]:
    return [r.summary_json() for r in runs.STORE.list_for(user.id)]


@app.post("/runs", status_code=201)
async def create_run(
    brief: str = Form(..., min_length=1, max_length=20_000),
    files: list[UploadFile] = File(default=[]),
    user: auth.User = Depends(auth.current_user),
) -> dict:
    brief = brief.strip()
    if len(brief) < config.LIMITS["briefMinChars"]:
        raise HTTPException(422, "Say a little more to get started.")
    input_files = await _admit_uploads(files)
    run = runs.STORE.create(user.id, brief)
    run.inputs = [f.as_dict() for f in input_files]
    asyncio.get_running_loop().create_task(runs.execute(run, input_files))
    return {"id": run.id}


@app.get("/runs/{run_id}")
def get_run(run_id: str, user: auth.User = Depends(auth.current_user)) -> dict:
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return run.full_json()


class FeedbackBody(BaseModel):
    rating: Literal["up", "down"] | None = None
    comment: str | None = Field(default=None, max_length=2_000)


@app.post("/runs/{run_id}/feedback", status_code=204)
def set_run_feedback(
    run_id: str, body: FeedbackBody, user: auth.User = Depends(auth.current_user)
) -> None:
    comment = (body.comment or "").strip() or None
    if not runs.STORE.set_feedback(user.id, run_id, body.rating, comment):
        raise HTTPException(404, "Run not found.")


class FollowUpBody(BaseModel):
    brief: str = Field(min_length=1, max_length=20_000)


@app.post("/runs/{run_id}/followup", status_code=201)
async def follow_up_run(
    run_id: str, body: FollowUpBody, user: auth.User = Depends(auth.current_user)
) -> dict:
    parent = runs.STORE.get(user.id, run_id)
    if parent is None:
        raise HTTPException(404, "Run not found.")
    ask = body.brief.strip()
    if len(ask) < config.LIMITS["briefMinChars"]:
        raise HTTPException(422, "Say a little more to continue.")
    run = runs.STORE.create_followup(user.id, ask, parent)
    asyncio.get_running_loop().create_task(runs.execute(run))
    return {"id": run.id}


@app.get("/runs/{run_id}/thread")
def run_thread(run_id: str, user: auth.User = Depends(auth.current_user)) -> list[dict]:
    """All turns of this run's session, oldest first — the full conversation."""
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    session_id = run.session_id or run.id
    return [t.full_json() for t in runs.STORE.session_turns(user.id, session_id)]


@app.get("/runs/{run_id}/artifacts/{name}")
async def download_artifact(
    run_id: str, name: str, user: auth.User = Depends(auth.current_user)
) -> Response:
    """Stream one delivered artifact's bytes. The run's own artifact list is the
    authorization boundary — only files this user's run actually published are
    served, so an unknown name (or a path-y one) is just a 404, never a read off
    disk by an attacker-chosen path."""
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    ref = next((a for a in run.artifacts if a.get("name") == name), None)
    if ref is None:
        raise HTTPException(404, "Artifact not found.")
    try:
        data = await LocalArtifactStore().get(ref["id"])
    except FileNotFoundError:
        raise HTTPException(404, "Artifact not found.")
    return Response(
        content=data,
        media_type=ref.get("mime") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{ref["name"]}"'},
    )


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, user: auth.User = Depends(auth.current_user)) -> StreamingResponse:
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return StreamingResponse(
        runs.sse_stream(run),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- memory ----------


class MemoryBody(BaseModel):
    tier: str
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=20_000)


def _wiki_json(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "tier": "wiki",
        "title": row["title"],
        "content": row["content"],
        "updatedAt": datetime.fromtimestamp(row["updated_at"], tz=timezone.utc).isoformat(),
    }


@app.get("/memory")
def list_memory(user: auth.User = Depends(auth.current_user)) -> list[dict]:
    with auth._db() as db:
        wiki = [
            _wiki_json(row)
            for row in db.execute(
                "SELECT * FROM wiki_entries WHERE user_id=? ORDER BY updated_at DESC", (user.id,)
            )
        ]
    episodic = [
        {
            "id": f"{run.id}_m{i}",
            "tier": "episodic",
            "title": f"Run: {run.title}",
            "content": write["content"],
            "updatedAt": write["ts"],
            "runId": run.id,
        }
        for run in runs.STORE.list_for(user.id)
        for i, write in enumerate(run.memory_writes)
    ]
    return wiki + episodic


@app.post("/memory", status_code=201)
def create_memory(body: MemoryBody, user: auth.User = Depends(auth.current_user)) -> dict:
    if body.tier != "wiki":
        raise HTTPException(403, "Only wiki memory is user-writable; other tiers are written by the pipeline.")
    entry_id = f"m_{secrets.token_hex(6)}"
    now = time.time()
    with auth._db() as db:
        db.execute(
            "INSERT INTO wiki_entries (id,user_id,title,content,updated_at) VALUES (?,?,?,?,?)",
            (entry_id, user.id, body.title, body.content, now),
        )
        row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
    return _wiki_json(row)


@app.put("/memory/{entry_id}")
def update_memory(entry_id: str, body: MemoryBody, user: auth.User = Depends(auth.current_user)) -> dict:
    with auth._db() as db:
        updated = db.execute(
            "UPDATE wiki_entries SET title=?, content=?, updated_at=? WHERE id=? AND user_id=?",
            (body.title, body.content, time.time(), entry_id, user.id),
        ).rowcount
        if not updated:
            raise HTTPException(404, "Memory entry not found.")
        row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
    return _wiki_json(row)


_UPLOAD_EXTENSIONS = {".md", ".markdown", ".txt"}
_UPLOAD_MAX_BYTES = 512 * 1024
_UPLOAD_MAX_FILES = 10


@app.post("/memory/upload", status_code=201)
async def upload_memory(
    files: list[UploadFile], user: auth.User = Depends(auth.current_user)
) -> list[dict]:
    """Bulk wiki import: each uploaded markdown/text file becomes an entry."""
    if not files:
        raise HTTPException(422, "No files received.")
    if len(files) > _UPLOAD_MAX_FILES:
        raise HTTPException(422, f"At most {_UPLOAD_MAX_FILES} files per upload.")
    created: list[dict] = []
    with auth._db() as db:
        for upload in files:
            name = os.path.basename(upload.filename or "untitled.md")
            stem, ext = os.path.splitext(name)
            if ext.lower() not in _UPLOAD_EXTENSIONS:
                raise HTTPException(422, f"{name}: only {', '.join(sorted(_UPLOAD_EXTENSIONS))} files are accepted.")
            raw = await upload.read()
            if len(raw) > _UPLOAD_MAX_BYTES:
                raise HTTPException(422, f"{name}: larger than 512 KB.")
            try:
                content = raw.decode("utf-8").strip()
            except UnicodeDecodeError:
                raise HTTPException(422, f"{name}: not valid UTF-8 text.")
            if not content:
                raise HTTPException(422, f"{name}: file is empty.")
            entry_id = f"m_{secrets.token_hex(6)}"
            now = time.time()
            db.execute(
                "INSERT INTO wiki_entries (id,user_id,title,content,updated_at) VALUES (?,?,?,?,?)",
                (entry_id, user.id, stem[:120] or "Untitled", content, now),
            )
            row = db.execute("SELECT * FROM wiki_entries WHERE id=?", (entry_id,)).fetchone()
            created.append(_wiki_json(row))
    return created


@app.delete("/memory/{entry_id}", status_code=204)
def delete_memory(entry_id: str, user: auth.User = Depends(auth.current_user)) -> None:
    with auth._db() as db:
        deleted = db.execute(
            "DELETE FROM wiki_entries WHERE id=? AND user_id=?", (entry_id, user.id)
        ).rowcount
    if not deleted:
        raise HTTPException(404, "Memory entry not found.")


# ---------- usage ----------


@app.get("/usage")
def usage(user: auth.User = Depends(auth.current_user)) -> dict:
    # Token metering lands with the Redis budget system; until then the
    # endpoint serves the plan budget with zero recorded spend.
    plan = next((p for p in config.PLANS if p["id"] == user.plan), config.PLANS[0])
    today = datetime.now(timezone.utc).date()
    by_day = [
        {"date": (today - timedelta(days=13 - i)).isoformat(), "tokens": 0}
        for i in range(14)
    ]
    return {
        "periodStart": by_day[0]["date"],
        "periodEnd": (today + timedelta(days=16)).isoformat(),
        "budget": plan["tokenBudget"],
        "used": 0,
        "byDay": by_day,
    }


# ---------- model settings (catalog lives in server/config.py) ----------


class ModelBody(BaseModel):
    layer: str
    model: str


@app.get("/settings/models")
def get_models(user: auth.User = Depends(auth.current_user)) -> list[dict]:
    with auth._db() as db:
        prefs = {
            row["layer"]: row["model"]
            for row in db.execute("SELECT layer, model FROM model_prefs WHERE user_id=?", (user.id,))
        }
    payload = []
    for entry in config.MODEL_CATALOG:
        item = {
            "layer": entry["layer"],
            "label": entry["label"],
            "description": entry["description"],
            "locked": entry["locked"],
            # locked layers always report the system default — user prefs
            # are ignored for them even if a row exists
            "model": entry["default"] if entry["locked"] else prefs.get(entry["layer"], entry["default"]),
            "options": entry["options"],
        }
        if entry["layer"] == "experts":
            # per-expert overrides: fall back to the experts default
            item["experts"] = [
                {
                    "key": expert["key"],
                    "label": expert["label"],
                    "model": prefs.get(f"expert:{expert['key']}") or item["model"],
                }
                for expert in config.EXPERTS
            ]
        payload.append(item)
    return payload


@app.put("/settings/models", status_code=204)
def set_model(body: ModelBody, user: auth.User = Depends(auth.current_user)) -> None:
    # per-expert overrides validate against the experts catalog entry
    if body.layer.startswith("expert:"):
        key = body.layer.removeprefix("expert:")
        if not any(e["key"] == key for e in config.EXPERTS):
            raise HTTPException(404, "Unknown expert.")
        entry = next(e for e in config.MODEL_CATALOG if e["layer"] == "experts")
    else:
        entry = next((e for e in config.MODEL_CATALOG if e["layer"] == body.layer), None)
    if entry is None:
        raise HTTPException(404, "Unknown layer.")
    if entry["locked"]:
        # the verifier and output filter are security gates — their models
        # are system policy, never a user preference
        raise HTTPException(403, "This layer is system-managed and cannot be changed.")
    if body.model not in entry["options"]:
        raise HTTPException(422, "Model not available for this layer.")
    with auth._db() as db:
        db.execute(
            "INSERT INTO model_prefs (user_id, layer, model) VALUES (?,?,?) "
            "ON CONFLICT(user_id, layer) DO UPDATE SET model=excluded.model",
            (user.id, body.layer, body.model),
        )


# ---------- billing (Stripe lands post-checkpoint) ----------


@app.post("/billing/checkout")
def checkout(user: auth.User = Depends(auth.current_user)) -> dict:
    raise HTTPException(501, "Billing is not wired yet — Stripe checkout arrives with the cloud release.")


@app.post("/billing/portal")
def billing_portal(user: auth.User = Depends(auth.current_user)) -> dict:
    raise HTTPException(501, "Billing is not wired yet — Stripe portal arrives with the cloud release.")
