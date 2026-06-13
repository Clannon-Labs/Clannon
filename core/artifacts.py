"""
Local-filesystem ArtifactStore — the dev/default implementation of the artifact
store contract (foundation.ArtifactStore). Stores delivered artifacts under a base
directory, one folder per run, retrievable by id. Swap for an R2-backed store in
production behind the same port; nothing else changes.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from foundation import ArtifactRef, get_root

_BASE_ENV = "VRAKSHA_ARTIFACTS_DIR"
_MAX_NAME = 200


def _base_dir() -> Path:
    env = os.getenv(_BASE_ENV)
    base = Path(env) if env else (get_root() / "server" / "data" / "artifacts")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_name(name: str) -> str:
    """Flatten to a single confined path component — no directories, no escape."""
    flat = str(name).replace("\\", "/").split("/")[-1].strip()
    if not flat or flat in {".", ".."} or "\x00" in flat:
        raise ValueError(f"invalid artifact name: {name!r}")
    return flat[:_MAX_NAME]


class LocalArtifactStore:
    """Filesystem ArtifactStore (satisfies foundation.ArtifactStore)."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _base_dir()

    def _run_dir(self, run_id: str) -> Path:
        d = self._base / _safe_name(run_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _mime(name: str) -> str:
        return mimetypes.guess_type(name)[0] or "application/octet-stream"

    async def put(self, run_id: str, name: str, data: bytes) -> ArtifactRef:
        fname = _safe_name(name)
        (self._run_dir(run_id) / fname).write_bytes(data)
        return ArtifactRef(
            id=f"{_safe_name(run_id)}/{fname}", run_id=run_id,
            name=fname, mime=self._mime(fname), size=len(data),
        )

    async def get(self, artifact_id: str) -> bytes:
        run_id, _, name = str(artifact_id).partition("/")
        return (self._base / _safe_name(run_id) / _safe_name(name)).read_bytes()

    async def list(self, run_id: str) -> list[ArtifactRef]:
        d = self._base / _safe_name(run_id)
        if not d.is_dir():
            return []
        return [
            ArtifactRef(
                id=f"{_safe_name(run_id)}/{p.name}", run_id=run_id,
                name=p.name, mime=self._mime(p.name), size=p.stat().st_size,
            )
            for p in sorted(d.glob("*")) if p.is_file()
        ]
