"""File-read tool (key: fs.read) — reads a text file from the calling expert's
workspace. Confined to the workspace; the path can never escape it. (To list files,
run `ls -R` via code.run — the sandbox gives a full shell.)"""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel, WorkspacePort

from registry import tool

_MAX_READ = 40_000  # chars returned; longer files are truncated


class FsReadIn(BaseModel):
    path: str = Field(description="Workspace-relative file path to read, e.g. 'src/app.py'. Cannot escape the workspace.")


class FsReadOut(BaseModel):
    ok: bool
    content: str = ""
    truncated: bool = False
    error: str = ""


@tool
class FileReadTool:
    name = "read"
    domain = "fs"
    description = "Read a text file at a workspace-relative path and return its content."
    input_schema = FsReadIn
    output_schema = FsReadOut
    permission = PermissionLevel.READ
    wants_workspace = True

    async def run(self, args: FsReadIn, workspace: WorkspacePort) -> FsReadOut:
        try:
            content = await workspace.read(args.path)
        except Exception as exc:  # noqa: BLE001 — missing/confinement/IO error -> structured failure
            return FsReadOut(ok=False, error=str(exc)[:200])
        if len(content) > _MAX_READ:
            return FsReadOut(ok=True, content=content[:_MAX_READ], truncated=True)
        return FsReadOut(ok=True, content=content)
