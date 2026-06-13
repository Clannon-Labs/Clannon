"""Code-run tool (key: code.run) — runs a shell command in the calling expert's
sandboxed workspace (no network, resource-limited, time-bounded) and returns the
exit code + captured output. Distinct from code.python_exec (in-process
RestrictedPython): this runs against real files in the Docker-isolated workspace, so
it can run scripts, test runners, and shell commands. Needs a per-run workspace."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel, WorkspacePort

from registry import tool


class CodeRunIn(BaseModel):
    command: str = Field(
        description="A shell command to run in the workspace sandbox, e.g. "
        "'python app.py', 'python -m pytest -q', 'python -m unittest', 'ls -R'."
    )


class CodeRunOut(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


@tool
class CodeRunTool:
    name = "run"
    domain = "code"
    description = "Run a shell command (python, a test runner, ls, etc.) in the sandboxed workspace; returns exit code, stdout, and stderr."
    input_schema = CodeRunIn
    output_schema = CodeRunOut
    permission = PermissionLevel.EXECUTE
    timeout_s = 300.0   # generous: first run may start the container; then the command runs
    wants_workspace = True

    async def run(self, args: CodeRunIn, workspace: WorkspacePort) -> CodeRunOut:
        r = await workspace.run(args.command)
        return CodeRunOut(exit_code=r.exit_code, stdout=r.stdout, stderr=r.stderr, timed_out=r.timed_out)
