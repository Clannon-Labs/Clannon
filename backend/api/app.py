"""
The FastAPI application — serves the contract in clannon/frontend/README.md.

    .venv/bin/uvicorn api.app:app --port 8000

Set FRONTEND_ORIGIN for CORS (default http://localhost:3000). Loads .env /
.env.local exactly like main.py so the pipeline gets its provider keys.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from dotenv import load_dotenv

# Same env bootstrap as main.py — before anything builds provider clients.
load_dotenv(".env")
load_dotenv(".env.local", override=True)

from observability import configure_logging
import settings

# Route every run's traces (module logs, provider HTTP, warnings, decision log)
# to the one unified file, exactly like the CLI — before the pipeline imports below.
configure_logging()

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from core.artifacts import LocalArtifactStore
from . import audit as _audit, auth, config, runs
from . import decision_audit as _decisions
from . import run_revision
from .run_lineage import LineageError
from .run_requests import (
    admit_uploads as _admit_uploads,
    parse_session_models as _parse_session_models,
)
from .run_state import TERMINAL_STATUSES
from .config_validation import fail_fast_if_strict
from .hardening import install_hardening

fail_fast_if_strict()

log = logging.getLogger(__name__)

_WARMUP_TIMEOUT_S = 30.0
_DRAIN_TIMEOUT_S = 10.0


@asynccontextmanager
async def lifespan(application: FastAPI):
    # STARTUP: warm heavy dependencies under a bounded timeout; never hard-fail
    from core.warmup import warmup

    try:
        await asyncio.wait_for(warmup(), timeout=_WARMUP_TIMEOUT_S)
        log.info("startup: warmup completed")
    except asyncio.TimeoutError:
        log.warning(
            "startup: warmup timed out after %ss (dependencies load lazily)",
            _WARMUP_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("startup: warmup error (non-fatal): %s", exc)

    yield

    # SHUTDOWN: signal cancellation to every in-flight run, then drain
    live_tasks = []
    for run in list(runs.STORE._runs.values()):
        if run.status not in TERMINAL_STATUSES:
            runs.STORE.request_cancel(run.user_id, run.id)
            if run.task is not None and not run.task.done():
                live_tasks.append(run.task)

    if live_tasks:
        log.info("shutdown: draining %d in-flight run(s)", len(live_tasks))
        try:
            await asyncio.wait_for(
                asyncio.gather(*live_tasks, return_exceptions=True),
                timeout=_DRAIN_TIMEOUT_S,
            )
            log.info("shutdown: drain complete")
        except asyncio.TimeoutError:
            log.warning("shutdown: drain timed out after %ss; proceeding", _DRAIN_TIMEOUT_S)
    else:
        log.info("shutdown: no in-flight runs to drain")


app = FastAPI(title="Clannon API (Vraksha engine)", version=config.VERSION, lifespan=lifespan)
app.include_router(run_revision.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,   # apex + workspace subdomain in prod; FRONTEND_ORIGIN by default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_hardening(app)


@app.exception_handler(LineageError)
async def lineage_error(_request: Request, _exc: LineageError) -> JSONResponse:
    """Fail closed without exposing which stored prefix row was unavailable."""
    return JSONResponse(
        {
            "detail": (
                "Conversation lineage is unavailable. Start a new conversation "
                "or retry from an earlier readable turn."
            )
        },
        status_code=409,
    )


# ---------- infrastructure (unauthenticated; expose ONLY process + dependency state) ----------


@app.get("/health")
def health() -> dict:
    """Liveness probe: 200 whenever the process is up. No dependency calls."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe: 200 when all dependencies are healthy, 503 when any is down.
    Body is a per-dependency status map; no user or tenant data is ever included."""
    from ._health import probe_db, probe_embeddings, probe_qdrant

    qdrant, emb, db = await asyncio.gather(
        probe_qdrant(),
        asyncio.to_thread(probe_embeddings),
        asyncio.to_thread(probe_db),
    )
    deps = {"qdrant": qdrant, "embeddings": emb, "db": db}
    healthy = all(v == "up" for v in deps.values())
    return JSONResponse(
        {"status": "healthy" if healthy else "degraded", "deps": deps},
        status_code=200 if healthy else 503,
    )


# ---------- public config (read-only sync) ----------


@app.get("/config")
def get_config() -> dict:
    return config.remote_config()


# ---------- auth ----------

# Sliding-window rate limit on credential endpoints (per client IP):
# blunts brute-force and signup flooding. In-memory is fine per-process;
# Redis takes over when the cloud deployment lands. Limits live in config.
_auth_attempts: dict[str, list[float]] = {}


def _auth_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    recent = [t for t in _auth_attempts.get(ip, []) if now - t < config.AUTH_RATE_WINDOW_S]
    if len(recent) >= config.AUTH_RATE_MAX_ATTEMPTS:
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


# ---------- projects ----------

# A project = a client or body of work. Runs and memory are scoped to it. The
# "current project" is CLIENT-side state — the frontend sends `projectId` per request;
# there is no server-side "active project".


class ProjectCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, max_length=24)
    # optional onboarding: when present, also seed a first WIKI entry in this project
    # (the "tell Clannon about this client" step), titled "Client: <name> — context".
    seedFacts: str | None = Field(default=None, max_length=20_000)


class ProjectRenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _project_json(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "color": p.get("color"),
        "createdAt": datetime.fromtimestamp(p["created_at"], tz=timezone.utc).isoformat(),
    }


def _require_project(user_id: str, project_id: str | None) -> str | None:
    """A `projectId` from a request is trusted ONLY after the ownership row confirms it
    (never trust an id from the body/query). Empty/None -> None (no project). An id that
    isn't this user's -> 422, so a client can't tag its data into someone else's project."""
    pid = (project_id or "").strip()
    if not pid:
        return None
    if auth.project_get(user_id, pid) is None:
        raise HTTPException(422, "Unknown project.")
    return pid


@app.get("/projects")
def list_projects(user: auth.User = Depends(auth.current_user)) -> list[dict]:
    """The user's projects, newest activity first."""
    return [_project_json(p) for p in auth.project_list(user.id)]


@app.post("/projects", status_code=201)
def create_project(body: ProjectCreateBody, user: auth.User = Depends(auth.current_user)) -> dict:
    name = body.name.strip()
    project = auth.project_create(user.id, name, body.color)
    seed = (body.seedFacts or "").strip()
    if seed:
        auth.wiki_create(user.id, f"Client: {name} — context", seed, project_id=project["id"])
    return _project_json(project)


@app.patch("/projects/{project_id}")
def rename_project(
    project_id: str, body: ProjectRenameBody, user: auth.User = Depends(auth.current_user)
) -> dict:
    project = auth.project_rename(user.id, project_id, body.name.strip())
    if project is None:
        raise HTTPException(404, "Project not found.")
    return _project_json(project)


@app.delete("/projects/{project_id}", status_code=204)
def remove_project(project_id: str, user: auth.User = Depends(auth.current_user)) -> Response:
    """Cascade-delete a project AND its runs (+ stored files) AND its wiki/memory scope,
    owner-scoped. Idempotent: a project with nothing left for this caller (or not theirs)
    is a no-op 204, never revealed — same semantics as delete-session."""
    runs.STORE.delete_project(user.id, project_id)
    return Response(status_code=204)


# ---------- runs ----------


# Run creation is multipart so a brief can carry optional input files (a CSV to
# analyze, code to work on). Files are malware-scanned at this boundary and the
# clean originals are seeded into the expert workspace; the brief still crosses
# the full pipeline. Limits live in config (one source, surfaced via /config).


@app.get("/runs")
def list_runs(
    projectId: str | None = None, user: auth.User = Depends(auth.current_user)
) -> list[dict]:
    """The user's runs, newest first — filtered to one project when `projectId` is given,
    all of them when omitted (backward-compatible)."""
    return [r.summary_json() for r in runs.STORE.list_for(user.id, projectId)]


@app.post("/runs", status_code=201)
async def create_run(
    brief: str = Form(..., min_length=1, max_length=config.BRIEF_MAX_CHARS),
    files: list[UploadFile] = File(default=[]),
    models: str = Form(default=""),
    projectId: str = Form(default=""),
    user: auth.User = Depends(auth.current_user),
) -> dict:
    brief = brief.strip()
    if len(brief) < config.LIMITS["briefMinChars"]:
        raise HTTPException(422, "Say a little more to get started.")
    project_id = _require_project(user.id, projectId)
    input_files = await _admit_uploads(files)
    session_models = _parse_session_models(models)
    run = runs.STORE.create(user.id, brief, project_id)
    run.session_models = session_models
    # Register before any post-creation await: once STORE exposes the run, every
    # cancellation path must have a live task to stop.
    run.task = asyncio.get_running_loop().create_task(runs.execute(run, input_files))
    return {"id": run.id}


@app.get("/runs/{run_id}")
def get_run(run_id: str, user: auth.User = Depends(auth.current_user)) -> dict:
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return run.full_json()


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user: auth.User = Depends(auth.current_user)) -> Response:
    """Cooperatively stop an in-flight run. Ownership-scoped (a run the caller doesn't
    own is a 404, never revealed). Idempotent: cancelling an already-terminal run is a
    no-op 204. For a live run, the task is signalled to stop and the authoritative
    `cancelled` status arrives over the SSE stream — the 200 body is informational.
    Cancel ≠ delete: the run stays in history with a `cancelled` status."""
    outcome = runs.STORE.request_cancel(user.id, run_id)
    if outcome == "notfound":
        raise HTTPException(404, "Run not found.")
    if outcome == "noop":
        return Response(status_code=204)  # already terminal — idempotent success
    return JSONResponse(
        {"status": outcome}, status_code=200
    )  # "cancelling" | direct-finalized "cancelled" | persistence "failed"


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


@app.post("/runs/{run_id}/followup", status_code=201)
async def follow_up_run(
    run_id: str,
    brief: str = Form(..., min_length=1, max_length=config.BRIEF_MAX_CHARS),
    files: list[UploadFile] = File(default=[]),
    models: str = Form(default=""),
    user: auth.User = Depends(auth.current_user),
) -> dict:
    # a follow-up turn carries the same input types as a root run: multipart
    # brief + optional files, admitted (malware-scanned, original bytes) exactly
    # like POST /runs, and seeded into the expert workspace for this turn. It can
    # also carry its own per-session model choices.
    parent = runs.STORE.get(user.id, run_id)
    if parent is None:
        raise HTTPException(404, "Run not found.")
    ask = brief.strip()
    if len(ask) < config.LIMITS["briefMinChars"]:
        raise HTTPException(422, "Say a little more to continue.")
    input_files = await _admit_uploads(files)
    session_models = _parse_session_models(models)
    run = runs.STORE.create_followup(user.id, ask, parent)
    run.session_models = session_models
    # Match root-run ordering: registration is atomic with exposing the run.
    run.task = asyncio.get_running_loop().create_task(runs.execute(run, input_files))
    return {"id": run.id}


@app.get("/runs/{run_id}/thread")
def run_thread(run_id: str, user: auth.User = Depends(auth.current_user)) -> list[dict]:
    """All effective turns of this branch, oldest first."""
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return [t.full_json() for t in runs.STORE.effective_thread(user.id, run)]


@app.get("/runs/{run_id}/audit")
def run_audit(run_id: str, user: auth.User = Depends(auth.current_user)) -> list[dict]:
    """Security-decision audit records for one run, scoped to its owner.

    Returns an empty list when the run was not blocked by a security gate, or
    when no audit records exist for this run (e.g. pre-audit runs). 404 when the
    run does not belong to the authenticated user."""
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return [_audit.public_json(r) for r in _audit.get_for_run(user.id, run_id)]


@app.get("/runs/{run_id}/decisions")
def run_decisions(run_id: str, user: auth.User = Depends(auth.current_user)) -> list[dict]:
    """Institutional decision-memory records for one run (CB4), in decision order,
    scoped to its owner. Empty list when the run made no discrete tool_call/answer
    decisions, or for a pre-CB4 run. 404 when the run does not belong to the
    authenticated user."""
    run = runs.STORE.get(user.id, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return [_decisions.public_json(r) for r in _decisions.get_for_run(user.id, run_id)]


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, user: auth.User = Depends(auth.current_user)) -> Response:
    """Permanently delete a whole conversation (every turn in the session), scoped to
    its owner. Idempotent: a session with nothing left for this caller is a no-op 204 —
    a session that isn't theirs simply has nothing to delete and is never revealed
    (204, not 404). The conversation and its turns are removed; the assistant's learned
    cross-session memory is retained."""
    runs.STORE.delete_session(user.id, session_id)
    return Response(status_code=204)


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
    projectId: str | None = None


def _wiki_json(entry: dict) -> dict:
    """Format a raw wiki entry (from the auth data layer) as the API shape."""
    return {
        "id": entry["id"],
        "tier": "wiki",
        "title": entry["title"],
        "content": entry["content"],
        "updatedAt": datetime.fromtimestamp(entry["updated_at"], tz=timezone.utc).isoformat(),
        "projectId": entry.get("project_id"),
    }


@app.get("/memory")
def list_memory(
    projectId: str | None = None, user: auth.User = Depends(auth.current_user)
) -> list[dict]:
    """The user's memory (wiki + episodic), filtered to one project when `projectId` is
    given, all of it when omitted."""
    wiki = [_wiki_json(entry) for entry in auth.wiki_list(user.id, projectId)]
    episodic = [
        {
            "id": f"{run.id}_m{i}",
            "tier": "episodic",
            "title": f"Run: {run.title}",
            "content": write["content"],
            "updatedAt": write["ts"],
            "runId": run.id,
            "projectId": run.project_id,
        }
        for run in runs.STORE.list_for(user.id, projectId)
        for i, write in enumerate(run.memory_writes)
    ]
    return wiki + episodic


_PREVIEW_MAX_ITEMS = 8    # frontend renders a compact panel; the Manager already ranks
_PREVIEW_MIN_CHARS = 3    # don't hydrate on a keystroke or two


@app.get("/memory/hydration-preview")
async def hydration_preview(
    brief: str = "",
    projectId: str | None = None,
    user: auth.User = Depends(auth.current_user),
) -> list[dict]:
    """Preview what the Memory Manager would hydrate for a draft brief, BEFORE a run
    exists — a read-only dry-run through the same `MemoryPort.hydrate` door with the
    same `user_id` scoping (never a second access path). Ranked by the Manager's real
    trust + similarity + recency ordering, capped for the panel. Best-effort: a short
    brief, degraded memory, or a memory fault returns [] — a preview never 5xxs."""
    text = (brief or "").strip()
    if len(text) < _PREVIEW_MIN_CHARS:
        return []
    from core.memory import manager  # the MemoryPort door (lazy: heavy deps)
    from foundation import HydrationRequest, NormalizedInput

    wiki_entries = auth.wiki_list(user.id, projectId)
    try:
        pkg = await manager.hydrate(HydrationRequest(
            session_id="",   # preview: no session, no run — provenance stays empty
            user_id=user.id,
            normalized=NormalizedInput(modality="text", content_type="text/plain", content=text),
            wiki=HydrationRequest.wiki_pairs(wiki_entries),
        ))
    except Exception:  # noqa: BLE001 — best-effort preview, never an error surface
        return []
    if pkg.degraded:
        return []

    # MemoryEntry shape (like GET /memory) + `score`. Wiki items map back to their
    # real entries (hydration keeps wiki as verbatim text); learned-tier items have
    # no API id, so they get a stable preview id + a derived title.
    wiki_by_content = {e["content"]: e for e in wiki_entries}
    out: list[dict] = []
    for i, item in enumerate(pkg.items[:_PREVIEW_MAX_ITEMS]):
        entry = wiki_by_content.get(item.content) if item.store.value == "wiki" else None
        if entry is not None:
            id_, title = entry["id"], entry["title"]
            updated = datetime.fromtimestamp(entry["updated_at"], tz=timezone.utc).isoformat()
            project = entry.get("project_id")
        else:
            id_ = f"preview_{i}"
            first_line = next((ln.strip() for ln in item.content.splitlines() if ln.strip()), "Memory")
            title = first_line[:80]
            created = getattr(item, "created_at", 0.0)
            updated = datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None
            project = None
        out.append({
            "id": id_,
            "tier": item.store.value,
            "title": title,
            "content": item.content,
            "updatedAt": updated,
            "projectId": project,
            "score": max(0.0, min(1.0, float(item.score))),
        })
    return out


@app.post("/memory", status_code=201)
def create_memory(body: MemoryBody, user: auth.User = Depends(auth.current_user)) -> dict:
    if body.tier != "wiki":
        raise HTTPException(403, "Only wiki memory is user-writable; other tiers are written by the pipeline.")
    project_id = _require_project(user.id, body.projectId)
    return _wiki_json(auth.wiki_create(user.id, body.title, body.content, project_id))


@app.put("/memory/{entry_id}")
def update_memory(entry_id: str, body: MemoryBody, user: auth.User = Depends(auth.current_user)) -> dict:
    entry = auth.wiki_update(user.id, entry_id, body.title, body.content)
    if entry is None:
        raise HTTPException(404, "Memory entry not found.")
    return _wiki_json(entry)


@app.post("/memory/upload", status_code=201)
async def upload_memory(
    request: Request,
    files: list[UploadFile] = File(...),
    projectId: str = Form(default=""),
    user: auth.User = Depends(auth.current_user),
) -> list[dict]:
    """Bulk wiki import: each uploaded markdown/text file becomes an entry. Scoped to the project
    given as EITHER the `projectId` multipart form field OR a `?projectId=` query param — so it
    scopes however the frontend sends it (its other scoped calls use the query string). An
    unknown/other-user project is a 422; absent -> unscoped / account default."""
    pid = (projectId or request.query_params.get("projectId") or "").strip()
    project_id = _require_project(user.id, pid)
    if not files:
        raise HTTPException(422, "No files received.")
    if len(files) > config.WIKI_UPLOAD_MAX_FILES:
        raise HTTPException(422, f"At most {config.WIKI_UPLOAD_MAX_FILES} files per upload.")
    entries: list[tuple[str, str]] = []
    for upload in files:
        name = os.path.basename(upload.filename or "untitled.md")
        stem, ext = os.path.splitext(name)
        if ext.lower() not in config.WIKI_UPLOAD_EXTENSIONS:
            raise HTTPException(422, f"{name}: only {', '.join(config.WIKI_UPLOAD_EXTENSIONS)} files are accepted.")
        raw = await upload.read()
        if len(raw) > config.WIKI_UPLOAD_MAX_BYTES:
            raise HTTPException(422, f"{name}: larger than {config.WIKI_UPLOAD_MAX_BYTES // 1024} KB.")
        try:
            content = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise HTTPException(422, f"{name}: not valid UTF-8 text.")
        if not content:
            raise HTTPException(422, f"{name}: file is empty.")
        entries.append((stem[:120] or "Untitled", content))
    return [_wiki_json(e) for e in auth.wiki_bulk_create(user.id, entries, project_id)]


@app.delete("/memory/{entry_id}", status_code=204)
def delete_memory(entry_id: str, user: auth.User = Depends(auth.current_user)) -> None:
    """Delete a memory entry, owner-scoped. A WIKI entry (id ``m_…``) is removed from the store;
    an EPISODIC entry (id ``<run_id>_m<i>``, a pipeline-written recollection) is dropped from its
    run so it stops appearing — the user's "that's outdated" action. 404 if neither matches."""
    if runs.STORE.forget_memory_write(user.id, entry_id):
        return
    if not auth.wiki_delete(user.id, entry_id):
        raise HTTPException(404, "Memory entry not found.")


# ---------- usage ----------


@app.get("/usage")
def usage(user: auth.User = Depends(auth.current_user)) -> dict:
    """Real metered usage for the current period: the actual tokens this user's runs
    spent (run.tokensUsed, summed over a trailing 30-day window) against their plan's
    monthly budget. The Redis-atomic budget ENFORCEMENT (decrement + hard stop) lands
    separately; this is the read-only view the sidebar meter and Settings render."""
    plan = next((p for p in config.PLANS if p["id"] == user.plan), config.PLANS[0])
    today = datetime.now(timezone.utc).date()
    window = settings.BUDGET.usage_metering_window_days   # D10: trailing window from config
    start = today - timedelta(days=window - 1)
    by_day = {(start + timedelta(days=i)).isoformat(): 0 for i in range(window)}
    for r in runs.STORE.list_for(user.id):
        try:
            day = datetime.fromisoformat(r.created_at).astimezone(timezone.utc).date().isoformat()
        except (TypeError, ValueError):
            continue
        if day in by_day:
            by_day[day] += int(getattr(r, "tokens_used", 0) or 0)
    return {
        "periodStart": start.isoformat(),
        "periodEnd": today.isoformat(),
        "budget": plan["tokenBudget"],
        "used": sum(by_day.values()),
        "byDay": [{"date": d, "tokens": t} for d, t in by_day.items()],
    }


# ---------- model settings (catalog lives in api/config.py) ----------


class ModelBody(BaseModel):
    layer: str
    model: str


@app.get("/settings/models")
def get_models(user: auth.User = Depends(auth.current_user)) -> list[dict]:
    """The per-role model catalog with the user's workspace choices applied: one entry
    per role (5 selectable + verifier/filter read-only). `model` is the user's choice or
    the role's default; `default` is the system default; `experts` lists what the role
    drives (informational)."""
    prefs = auth.model_prefs_get(user.id)
    return [
        {
            "layer": entry["layer"],
            "label": entry["label"],
            "description": entry["description"],
            "locked": entry["locked"],
            # locked roles always report the system default — user prefs are ignored
            "model": entry["default"] if entry["locked"] else prefs.get(entry["layer"], entry["default"]),
            "default": entry["default"],
            "options": entry["options"],
            "experts": entry["experts"],
        }
        for entry in config.MODEL_CATALOG
    ]


@app.put("/settings/models", status_code=204)
def set_model(body: ModelBody, user: auth.User = Depends(auth.current_user)) -> None:
    """Set the user's WORKSPACE default model for a role (applied to every new run unless
    a per-session choice overrides it). `layer` is a role; locked roles are 403."""
    entry = next((e for e in config.MODEL_CATALOG if e["layer"] == body.layer), None)
    if entry is None:
        raise HTTPException(404, "Unknown role.")
    if entry["locked"]:
        # the verifier and output filter are security gates — their models
        # are system policy, never a user preference
        raise HTTPException(403, "This role is system-managed and cannot be changed.")
    if body.model not in entry["options"]:
        raise HTTPException(422, "Model not available for this role.")
    auth.model_prefs_set(user.id, body.layer, body.model)


# ---------- billing (Stripe lands post-checkpoint) ----------


@app.post("/billing/checkout")
def checkout(user: auth.User = Depends(auth.current_user)) -> dict:
    raise HTTPException(501, "Billing is not wired yet — Stripe checkout arrives with the cloud release.")


@app.post("/billing/portal")
def billing_portal(user: auth.User = Depends(auth.current_user)) -> dict:
    raise HTTPException(501, "Billing is not wired yet — Stripe portal arrives with the cloud release.")
