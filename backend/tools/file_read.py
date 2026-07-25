"""File-read tool (key: fs.read) — reads a text file from the calling expert's
workspace. Confined to the workspace; the path can never escape it. (To list files,
run `ls -R` via code.run — the sandbox gives a full shell.)

Optional `start_line`/`end_line` read a precise 1-indexed inclusive slice instead of
the whole file, returned with `cat -n`-style line numbers so the caller can name exact
lines for a subsequent `fs.patch` — and, for a file bigger than `_MAX_READ`, this is
the ONLY way to reach content past the truncation point (a whole-file read still
truncates, unchanged)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from foundation import PermissionLevel, WorkspacePort

from registry import tool

_MAX_READ = 40_000  # chars returned; longer WHOLE-FILE reads are truncated
_MAX_RANGE_LINES = 2_000  # a ranged read is bounded by line count, not chars


class FsReadIn(BaseModel):
    path: str = Field(description="Workspace-relative file path to read, e.g. 'src/app.py'. Cannot escape the workspace.")
    start_line: int | None = Field(
        default=None, ge=1,
        description="1-indexed inclusive start line for a precise slice instead of the whole file. "
        "Omit both start_line and end_line to read the whole file (subject to the char cap).",
    )
    end_line: int | None = Field(
        default=None, ge=1,
        description="1-indexed inclusive end line for a precise slice. Must be given together with start_line.",
    )

    @model_validator(mode="after")
    def _range_is_paired_and_ordered(self) -> "FsReadIn":
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("start_line and end_line must be given together")
        if self.start_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class FsReadOut(BaseModel):
    ok: bool
    content: str = ""
    truncated: bool = False
    error: str = ""


@tool
class FileReadTool:
    name = "read"
    domain = "fs"
    description = (
        "Read a text file at a workspace-relative path. Omit start_line/end_line for the whole "
        "file (long files are truncated); give both (1-indexed, inclusive) to read a precise, "
        "line-numbered slice — the only way to see content past the whole-file truncation point, "
        "and the way to find exact line numbers before calling fs.patch."
    )
    input_schema = FsReadIn
    output_schema = FsReadOut
    permission = PermissionLevel.READ
    wants_workspace = True

    async def run(self, args: FsReadIn, workspace: WorkspacePort) -> FsReadOut:
        try:
            content = await workspace.read(args.path)
        except Exception as exc:  # noqa: BLE001 — missing/confinement/IO error -> structured failure
            return FsReadOut(ok=False, error=str(exc)[:200])

        if args.start_line is None:
            if len(content) > _MAX_READ:
                return FsReadOut(ok=True, content=content[:_MAX_READ], truncated=True)
            return FsReadOut(ok=True, content=content)

        lines = content.splitlines()
        if args.start_line > len(lines):
            return FsReadOut(ok=False, error=f"start_line {args.start_line} is past end of file ({len(lines)} lines)")
        end = min(args.end_line, len(lines))
        selected = lines[args.start_line - 1:end]
        truncated = False
        if len(selected) > _MAX_RANGE_LINES:
            selected = selected[:_MAX_RANGE_LINES]
            truncated = True
        numbered = "\n".join(f"{args.start_line + i:>6}\t{line}" for i, line in enumerate(selected))
        return FsReadOut(ok=True, content=numbered, truncated=truncated)
