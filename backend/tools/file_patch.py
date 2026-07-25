"""File-patch tool (key: fs.patch) — replaces, inserts, or deletes a precise
1-indexed inclusive line range inside a workspace file, instead of overwriting the
whole file (fs.write). Read-modify-write against the existing confined
workspace.read/write — no new WorkspacePort method.

Precise patching over accepting a raw unified-diff blob, deliberately: no fuzzy
context-matching/offset-drift to get subtly wrong, and a caller that just read a
line-numbered range (fs.read's start_line/end_line) can cite exact line numbers
more reliably than it can emit a perfectly-formed diff. Pairs with fs.read to fix a
real correctness gap: fs.read truncates a whole-file read at 40k chars, and
fs.write is whole-file overwrite — editing anything bigger than that cap through
those two alone silently clobbers everything past the truncation point."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from foundation import PermissionLevel, WorkspacePort

from registry import tool

_MAX_REPLACEMENT_CHARS = 40_000  # matches fs.read's whole-file cap, for symmetry


class FsPatchIn(BaseModel):
    path: str = Field(description="Workspace-relative file path to patch, e.g. 'src/app.py'. Cannot escape the workspace.")
    start_line: int = Field(ge=1, description="1-indexed inclusive start of the line range to replace.")
    end_line: int = Field(
        description="1-indexed inclusive end of the line range to replace. Set to start_line - 1 to "
        "INSERT replacement before start_line instead of replacing anything. Must be >= start_line - 1.",
    )
    replacement: str = Field(
        default="",
        description="Text to put in place of the range (0, 1, or many lines). Empty deletes the range.",
    )

    @model_validator(mode="after")
    def _range_is_sane(self) -> "FsPatchIn":
        if self.end_line < self.start_line - 1:
            raise ValueError("end_line must be >= start_line - 1 (use start_line - 1 to insert)")
        if len(self.replacement) > _MAX_REPLACEMENT_CHARS:
            raise ValueError(f"replacement exceeds the {_MAX_REPLACEMENT_CHARS}-char cap")
        return self


class FsPatchOut(BaseModel):
    ok: bool
    path: str = ""
    lines_before: int = 0
    lines_after: int = 0
    error: str = ""


@tool
class FilePatchTool:
    name = "patch"
    domain = "fs"
    description = (
        "Replace, insert, or delete a precise 1-indexed inclusive line range in a text file — "
        "read the range first with fs.read's start_line/end_line to get exact line numbers, then "
        "patch it. Use this instead of fs.write for a targeted edit to any file you didn't just "
        "write from scratch, especially a file too big to read whole."
    )
    input_schema = FsPatchIn
    output_schema = FsPatchOut
    permission = PermissionLevel.WRITE
    wants_workspace = True

    async def run(self, args: FsPatchIn, workspace: WorkspacePort) -> FsPatchOut:
        try:
            content = await workspace.read(args.path)
        except Exception as exc:  # noqa: BLE001 — missing/confinement/IO error -> structured failure
            return FsPatchOut(ok=False, path=args.path, error=str(exc)[:200])

        lines = content.splitlines()
        n = len(lines)
        inserting = args.end_line == args.start_line - 1
        upper_bound = n + 1 if inserting else n
        if args.start_line > upper_bound:
            return FsPatchOut(
                ok=False, path=args.path, lines_before=n,
                error=f"line {args.start_line} is out of bounds ({n} lines in file)",
            )
        if not inserting and args.end_line > n:
            return FsPatchOut(
                ok=False, path=args.path, lines_before=n,
                error=f"end_line {args.end_line} is out of bounds ({n} lines in file)",
            )

        before = lines[:args.start_line - 1]
        after = lines[args.start_line - 1:] if inserting else lines[args.end_line:]
        inserted = args.replacement.splitlines() if args.replacement else []
        result = before + inserted + after
        new_content = "\n".join(result)
        if content.endswith("\n") and new_content:
            new_content += "\n"

        try:
            await workspace.write(args.path, new_content)
        except Exception as exc:  # noqa: BLE001 — confinement/IO error -> structured failure, never raise
            return FsPatchOut(ok=False, path=args.path, lines_before=n, error=str(exc)[:200])
        return FsPatchOut(ok=True, path=args.path, lines_before=n, lines_after=len(result))
