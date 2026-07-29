"""HTTP contract for revising one terminal conversation turn."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from . import auth, config, runs
from .run_requests import admit_uploads, parse_session_models
from .run_state import TERMINAL_STATUSES

router = APIRouter()


@router.post("/runs/{run_id}/revise", status_code=201)
async def revise_run(
    run_id: str,
    brief: str = Form(..., min_length=1, max_length=config.BRIEF_MAX_CHARS),
    files: list[UploadFile] = File(default=[]),
    models: str = Form(default=""),
    reuseInputs: bool = Form(default=True),
    user: auth.User = Depends(auth.current_user),
) -> dict:
    """Replace one turn and its suffix inside the target's existing session."""
    target = _terminal_target(user.id, run_id)
    edited = brief.strip()
    if len(edited) < config.LIMITS["briefMinChars"]:
        raise HTTPException(422, "Say a little more to continue.")

    replacements = await admit_uploads(files)
    session_models = parse_session_models(models)
    input_files = replacements
    if not replacements and reuseInputs:
        try:
            input_files = await runs.load_reusable_inputs(target)
        except runs.InputReuseError as exc:
            raise HTTPException(409, str(exc)) from exc

    # Scanning and blob reads yield. Re-authorize so concurrent deletion cannot
    # create a branch whose inherited rows vanished during preflight.
    target = _terminal_target(user.id, run_id)
    loop = asyncio.get_running_loop()
    run = runs.STORE.create_revision(
        user.id,
        edited,
        target,
        session_models=session_models,
        start=lambda revision: loop.create_task(runs.execute(revision, input_files)),
    )
    if run is None:
        raise HTTPException(404, "Run not found.")
    return {"id": run.id}


def _terminal_target(user_id: str, run_id: str):
    target = runs.STORE.get(user_id, run_id)
    if target is None:
        raise HTTPException(404, "Run not found.")
    if target.status not in TERMINAL_STATUSES:
        raise HTTPException(409, "Wait for this run to finish before revising it.")
    return target
