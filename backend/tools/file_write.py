"""File-write tool (key: fs.write) — writes a text file inside the calling expert's
workspace. Confined to the workspace; the path can never escape it. Needs a per-run
workspace (the handler injects it for workspace-scoped experts)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel, WorkspacePort

from registry import tool


class FsWriteIn(BaseModel):
    path: str = Field(description="Workspace-relative file path to write, e.g. 'src/app.py'. Cannot escape the workspace.")
    content: str = Field(description="The full text content to write to the file (create or overwrite).")


class FsWriteOut(BaseModel):
    ok: bool
    path: str = ""
    error: str = ""


@tool
class FileWriteTool:
    name = "write"
    domain = "fs"
    description = "Write a text file (create or overwrite) at a workspace-relative path."
    input_schema = FsWriteIn
    output_schema = FsWriteOut
    permission = PermissionLevel.WRITE
    wants_workspace = True

    async def run(self, args: FsWriteIn, workspace: WorkspacePort) -> FsWriteOut:
        try:
            await workspace.write(args.path, args.content)
            return FsWriteOut(ok=True, path=args.path)
        except Exception as exc:  # noqa: BLE001 — confinement/IO error -> structured failure, never raise
            return FsWriteOut(ok=False, path=args.path, error=str(exc)[:200])
