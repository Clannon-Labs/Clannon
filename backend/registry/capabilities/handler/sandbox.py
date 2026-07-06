"""
Docker-backed Workspace — the per-run sandbox behind `foundation.WorkspacePort`.

An expert that does real file/code work gets one of these for its run: a private
host directory (mounted as /workspace) for confined file I/O, and a locked-down
Docker container for running code against those files. It persists across the
expert's tool calls and is torn down when the run ends.

Persistence model: the FILES live on the host directory, which is bind-mounted into
the container. So the container is just recreatable compute — killing/recreating it
(on a timeout, a reset, or between commands) never loses the files. `reset()` wipes
the files for a clean slate; `close()` tears everything down.

SECURITY:
  - Code execution is OFF unless `VRAKSHA_ENABLE_SANDBOX=1`. File I/O always works
    (it is just a private temp dir).
  - File paths are confined to the workspace root — an absolute path or one that
    escapes via `..` or a symlink is rejected, never followed onto the host.
  - Generated code runs ONLY inside the container, which has no network, runs
    non-root, has a read-only root filesystem (only /workspace + a small /tmp tmpfs
    are writable), and is memory/CPU/pids-limited and time-bounded.

Production can swap this for a remote sandbox service by providing another
WorkspacePort; nothing else in the system changes.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import settings
from foundation import RunResult

# Resource caps + timeouts live in config/backend/security.yaml (settings.SECURITY) --
# ceiling-bounded fail-loud on the six that bound the sandboxed workload (docket D8).
# _ENABLE/_IMAGE_ENV/_DEFAULT_IMAGE stay here: security identity (a config value that
# could disable the sandbox or swap its image is a hole, not a dial), never a settings
# field. Same for the isolation STRUCTURE below (--network none, --read-only, non-root,
# the mount layout) -- boolean/structural, no numeric ceiling applies.
_ENABLE = "VRAKSHA_ENABLE_SANDBOX"
_IMAGE_ENV = "VRAKSHA_SANDBOX_IMAGE"
_DEFAULT_IMAGE = "python:3.12-slim"


def sandbox_enabled() -> bool:
    """Whether sandboxed code execution is allowed (file I/O is always allowed)."""
    return os.getenv(_ENABLE, "").strip().lower() in {"1", "true", "yes", "on"}


class DockerWorkspace:
    """A per-run isolated workspace (satisfies foundation.WorkspacePort)."""

    def __init__(self) -> None:
        self._root = Path(tempfile.mkdtemp(prefix="vraksha-ws-"))
        self._name = self._root.name           # reuse the unique dir name as the container name
        self._up = False                        # whether the container is running
        self._closed = False

    # --- file I/O (confined to the workspace root; no container needed) -------

    def _resolve(self, rel_path: str) -> Path:
        if not isinstance(rel_path, str) or not rel_path or rel_path.startswith("/") or "\x00" in rel_path:
            raise ValueError(f"invalid workspace path: {rel_path!r}")
        target = (self._root / rel_path).resolve()
        if not target.is_relative_to(self._root.resolve()):
            raise ValueError(f"path escapes the workspace: {rel_path!r}")
        return target

    async def write(self, rel_path: str, content: str) -> None:
        self._guard_open()
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    async def write_bytes(self, rel_path: str, data: bytes) -> None:
        self._guard_open()
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def read(self, rel_path: str) -> str:
        self._guard_open()
        return self._resolve(rel_path).read_text(encoding="utf-8")

    async def read_bytes(self, rel_path: str) -> bytes:
        self._guard_open()
        return self._resolve(rel_path).read_bytes()

    async def list(self) -> list[str]:
        self._guard_open()
        root = self._root.resolve()
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

    # --- sandboxed code execution (gated) -------------------------------------

    async def run(self, command: str, *, timeout_s: float | None = None) -> RunResult:
        self._guard_open()
        if not sandbox_enabled():
            return RunResult(-1, "", f"[sandbox disabled: set {_ENABLE}=1 to run code]", False)
        try:
            await self._ensure_container()
        except Exception as exc:  # noqa: BLE001 — docker missing/down/image issue: report, never raise
            return RunResult(-1, "", f"[sandbox unavailable: {str(exc)[:200]}]", False)
        return await self._exec(command, timeout_s or settings.SECURITY.sandbox_run_timeout_s)

    async def reset(self) -> None:
        """Fresh container AND clean files (a clean slate, as if newly opened)."""
        self._guard_open()
        await self._teardown_container()
        shutil.rmtree(self._root, ignore_errors=True)
        self._root = Path(tempfile.mkdtemp(prefix="vraksha-ws-"))
        self._name = self._root.name

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._teardown_container()
        shutil.rmtree(self._root, ignore_errors=True)

    # --- internals ------------------------------------------------------------

    def _guard_open(self) -> None:
        if self._closed:
            raise RuntimeError("workspace is closed")

    async def _ensure_container(self) -> None:
        if self._up:
            return
        image = os.getenv(_IMAGE_ENV) or _DEFAULT_IMAGE
        args = [
            "docker", "run", "-d", "--rm", "--name", self._name,
            "--network", "none",                                  # no network
            "--memory", f"{settings.SECURITY.sandbox_memory_mb}m",
            "--cpus", str(settings.SECURITY.sandbox_cpus),
            "--pids-limit", str(settings.SECURITY.sandbox_pids),
            "--read-only", "--tmpfs", f"/tmp:rw,size={settings.SECURITY.sandbox_tmpfs_mb}m",
            "-v", f"{self._root}:/workspace:rw",
            "-w", "/workspace",
        ]
        if hasattr(os, "getuid"):
            args += ["--user", f"{os.getuid()}:{os.getgid()}"]    # files stay host-owned
        args += [image, "sleep", "infinity"]
        code, out, err = await self._proc(args, timeout=settings.SECURITY.sandbox_create_timeout_s)
        if code != 0:
            raise RuntimeError((err or out).strip()[:200] or "docker run failed")
        self._up = True

    async def _exec(self, command: str, timeout: float) -> RunResult:
        try:
            code, out, err = await self._proc(
                ["docker", "exec", self._name, "sh", "-c", command], timeout=timeout
            )
        except asyncio.TimeoutError:
            # kill the container (files on the host dir survive; next run recreates it)
            await self._teardown_container()
            return RunResult(-1, "", f"[command timed out after {timeout:.0f}s]", True)
        cap = settings.SECURITY.sandbox_max_output_chars
        return RunResult(code, out[:cap], err[:cap], False)

    async def _teardown_container(self) -> None:
        if not self._up:
            return
        self._up = False
        await self._proc(  # best-effort
            ["docker", "rm", "-f", self._name], timeout=settings.SECURITY.sandbox_teardown_timeout_s,
        )

    @staticmethod
    async def _proc(args: list[str], *, timeout: float) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
