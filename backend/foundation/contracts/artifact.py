"""
ArtifactStore — the contract for durable output artifacts an expert produces.

An expert does its work in an ephemeral workspace; anything it wants to DELIVER (a
generated report, a code file, later a chart image) it names in `ExpertOutput.artifacts`,
and the handler copies those files OUT of the workspace into an ArtifactStore before the
workspace is torn down. The store keeps them durably and hands back an `ArtifactRef` the
rest of the pipeline can carry, surface, and serve.

Thin contract here; the implementation (local dir for dev, R2 for prod) lives behind it,
mirroring MemoryPort / WorkspacePort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A reference to one stored artifact (not its bytes)."""
    id: str          # store key, retrievable via ArtifactStore.get
    run_id: str      # the run this artifact belongs to
    name: str        # the file name the expert published, e.g. "report.md" / "chart.png"
    mime: str        # best-effort content type
    size: int        # bytes

    def as_dict(self) -> dict:
        return {"id": self.id, "run_id": self.run_id, "name": self.name, "mime": self.mime, "size": self.size}


@runtime_checkable
class ArtifactStore(Protocol):
    """Durable storage for delivered artifacts, scoped by run."""

    async def put(self, run_id: str, name: str, data: bytes) -> ArtifactRef:
        """Store `data` under (run_id, name) and return its reference."""
        ...

    async def get(self, artifact_id: str) -> bytes:
        """Fetch one artifact's bytes by its id."""
        ...

    async def list(self, run_id: str) -> list[ArtifactRef]:
        """All artifacts stored for a run."""
        ...
