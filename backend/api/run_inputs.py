"""Durable uploaded-input handling for current turns and conversation lineage."""

from __future__ import annotations

import hashlib
from typing import Any

from core.artifacts import LocalArtifactStore
from foundation import InputFile

from .run_state import RunState
from .run_store import INPUT_NS

_MAX_LINEAGE_FILES = 30
_MAX_LINEAGE_FILE_BYTES = 64 * 1024 * 1024


class InputReuseError(RuntimeError):
    """A target turn declared inputs that cannot be safely reconstructed."""


def _input_ns(run_id: str) -> str:
    return f"{INPUT_NS}{run_id}"


async def persist_inputs(run: RunState, input_files: list[Any]) -> None:
    """Persist scanned uploads for later turns and record integrity metadata."""
    store = LocalArtifactStore()
    entries: list[dict] = []
    for input_file in input_files:
        meta = input_file.as_dict()
        meta["_sha256"] = hashlib.sha256(input_file.data).hexdigest()
        try:
            meta["id"] = (
                await store.put(_input_ns(run.id), input_file.name, input_file.data)
            ).id
        except Exception:  # noqa: BLE001 — current in-memory input remains usable
            pass
        entries.append(meta)
    run.inputs = entries


async def load_reusable_inputs(run: RunState) -> list[InputFile]:
    """Rebuild target inputs only from owner-bound authoritative stored blobs.

    New rows carry hashes. Pre-hash rows remain safe to reuse because their artifact
    ID is pinned to the target run's private input namespace and their byte count is
    verified; client-supplied metadata never reaches this path.
    """
    store = LocalArtifactStore()
    files: list[InputFile] = []
    for meta in run.inputs or []:
        input_file = await _load_blob(store, run, meta, strict=True)
        if input_file is not None:
            files.append(input_file)
    return files


async def gather_lineage_files(
    store: Any, run: RunState, current: list[Any] | None
) -> list[Any]:
    """Load current and effective-prior uploads, bounded by count and bytes."""
    files = list(current or [])
    seen = {getattr(input_file, "name", "") for input_file in files}
    total = sum(int(getattr(input_file, "size", 0) or 0) for input_file in files)
    artifact_store = LocalArtifactStore()

    for turn in store.effective_thread(run.user_id, run):
        if turn.id == run.id or turn.created_at >= run.created_at:
            continue
        for meta in turn.inputs or []:
            if len(files) >= _MAX_LINEAGE_FILES or total >= _MAX_LINEAGE_FILE_BYTES:
                return files
            input_file = await _load_blob(artifact_store, turn, meta, strict=False)
            if input_file is None or input_file.name in seen:
                continue
            files.append(input_file)
            seen.add(input_file.name)
            total += input_file.size
    return files


async def _load_blob(
    store: LocalArtifactStore, run: RunState, meta: Any, *, strict: bool
) -> InputFile | None:
    try:
        if not isinstance(meta, dict):
            raise ValueError("input metadata is not an object")
        name = meta["name"]
        artifact_id = meta["id"]
        modality = meta["modality"]
        size = meta["size"]
        digest = meta.get("_sha256")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(artifact_id, str)
            or artifact_id != f"{_input_ns(run.id)}/{name}"
            or not isinstance(modality, str)
            or not isinstance(size, int)
            or size < 0
            or (digest is not None and (not isinstance(digest, str) or len(digest) != 64))
        ):
            raise ValueError("input metadata is malformed")
        data = await store.get(artifact_id)
        if (
            not isinstance(data, bytes)
            or len(data) != size
            or (digest is not None and hashlib.sha256(data).hexdigest() != digest)
        ):
            raise ValueError("input blob failed integrity validation")
        return InputFile(name=name, modality=modality, data=data, size=len(data))
    except Exception as exc:  # noqa: BLE001 — normalized below; no storage detail leaks
        if strict:
            label = meta.get("name", "input") if isinstance(meta, dict) else "input"
            raise InputReuseError(
                f"Original input {label!r} is unavailable. Upload a replacement "
                "or retry with reuseInputs=false."
            ) from exc
        return None
