"""
python_exec tool (key: code.python_exec) — run a small snippet in a restricted
sandbox and return its printed output.

SECURITY: in-process RestrictedPython is a hardening layer, NOT a strong sandbox
(escapes are a known risk). So execution is OFF by default and only runs when a
developer explicitly opts in via the VRAKSHA_ENABLE_PYTHON_EXEC env flag. Even
then it uses RestrictedPython's safer_getattr and curated safe_globals, and the
handler bounds it with TOOL_TIMEOUT_S.

TODO (before production / before enabling broadly): out-of-process isolation
(subprocess + seccomp/landlock, gVisor, or a no-network read-only container).
"""

from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Guards import safer_getattr
from RestrictedPython.PrintCollector import PrintCollector

from foundation import PermissionLevel

from ..registry import tool

_OPT_IN = "VRAKSHA_ENABLE_PYTHON_EXEC"


def _enabled() -> bool:
    return os.getenv(_OPT_IN, "").strip().lower() in {"1", "true", "yes"}


class PyExecIn(BaseModel):
    code: str


class PyExecOut(BaseModel):
    ok: bool
    output: str


@tool(
    name="python_exec",
    domain="code",
    description="Run a small snippet of restricted Python and return its printed output.",
    input_schema=PyExecIn,
    output_schema=PyExecOut,
    permission=PermissionLevel.EXECUTE,
    tags=("sandbox", "compute"),
)
class PythonExecTool:
    async def run(self, args: PyExecIn) -> PyExecOut:
        if not _enabled():
            return PyExecOut(
                ok=False,
                output=(
                    f"python_exec is disabled; set {_OPT_IN}=1 to enable. "
                    "In-process RestrictedPython is not a strong sandbox."
                ),
            )
        return await asyncio.to_thread(self._run_sync, args.code)

    @staticmethod
    def _run_sync(code: str) -> PyExecOut:
        try:
            byte_code = compile_restricted(code, "<vraksha-sandbox>", "exec")
        except SyntaxError as exc:
            return PyExecOut(ok=False, output=f"syntax error: {exc}")

        glb = dict(safe_globals)
        glb["_print_"] = PrintCollector
        glb["_getattr_"] = safer_getattr          # not raw getattr
        local: dict = {}
        try:
            exec(byte_code, glb, local)
        except Exception as exc:
            return PyExecOut(ok=False, output=f"error: {exc}")

        printer = local.get("_print") or glb.get("_print")
        printed = printer() if callable(printer) else ""
        return PyExecOut(ok=True, output=str(printed).strip())
