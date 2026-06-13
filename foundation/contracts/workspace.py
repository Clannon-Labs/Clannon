"""
WorkspacePort — the contract for a per-run isolated working space.

A workspace gives an expert a confined place to do real file and code work: read
and write files (paths are workspace-relative and CANNOT escape it) and run code in
a sandbox (no network, resource-limited). It persists across the expert's tool calls
within ONE run — so the expert can write, run a test, read the result, and continue
in the same space — and is torn down when the run ends.

Tools hold only this port (foundation-level, so `tools/` may import it). The actual
Docker-backed implementation lives in the handler layer and is injected per run.
This mirrors MemoryPort: a thin contract here, the real machinery behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RunResult:
    """The outcome of running one command in the workspace sandbox."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@runtime_checkable
class WorkspacePort(Protocol):
    """A per-run isolated workspace: confined file I/O + sandboxed code execution.

    Every `rel_path` is interpreted relative to the workspace root and confined to
    it — an absolute path or one that escapes the root (e.g. via `..` or a symlink)
    is rejected, never followed onto the host. The implementation owns all
    isolation; callers only see this surface.
    """

    async def write(self, rel_path: str, content: str) -> None:
        """Create/overwrite a text file at a workspace-relative path (confined)."""
        ...

    async def read(self, rel_path: str) -> str:
        """Read a text file at a workspace-relative path (confined)."""
        ...

    async def list(self) -> list[str]:
        """The workspace-relative paths of the files currently in the workspace."""
        ...

    async def run(self, command: str, *, timeout_s: float | None = None) -> RunResult:
        """Run a shell command inside the sandbox, with the workspace as the working
        directory, and return its exit code + captured (output-capped) stdout/stderr.
        No network; resource-limited; bounded by a timeout."""
        ...

    async def reset(self) -> None:
        """Discard the current sandbox + files and start fresh on next use."""
        ...

    async def close(self) -> None:
        """Tear down the sandbox and delete the workspace. Idempotent."""
        ...
