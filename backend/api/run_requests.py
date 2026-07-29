"""Shared multipart admission for run-creation routes."""

from __future__ import annotations

import json

from fastapi import HTTPException, UploadFile

from security.sanitizers import uploads as upload_scan

from . import config


def parse_session_models(models: str) -> dict[str, str]:
    """Return valid user-selectable role overrides from one JSON form field.

    A malformed container is a request error. Invalid individual entries are
    ignored so stale clients fall back to configured defaults.
    """
    if not models or not models.strip():
        return {}
    try:
        raw = json.loads(models)
    except (ValueError, TypeError):
        raise HTTPException(422, "`models` must be a JSON object of role -> model.")
    if not isinstance(raw, dict):
        raise HTTPException(422, "`models` must be a JSON object of role -> model.")

    by_role = {entry["layer"]: entry for entry in config.MODEL_CATALOG}
    chosen: dict[str, str] = {}
    for role, model in raw.items():
        entry = by_role.get(role)
        if entry is None or entry["locked"]:
            continue
        if model not in entry["options"]:
            continue
        chosen[role] = model
    return chosen


async def admit_uploads(files: list[UploadFile]) -> list:
    """Scan uploads once at API boundary and return admitted original bytes."""
    if not files:
        return []
    if len(files) > config.MAX_INPUT_FILES:
        raise HTTPException(422, f"At most {config.MAX_INPUT_FILES} files per run.")

    admitted = []
    for upload in files:
        data = await upload.read()
        item, reason = await upload_scan.scan_upload(upload.filename or "upload", data)
        if reason:
            raise HTTPException(422, reason)
        admitted.append(item)
    return admitted
