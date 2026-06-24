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

import builtins as _bi

from pydantic import BaseModel
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem
from RestrictedPython.Guards import (
    full_write_guard,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safer_getattr,
)
from RestrictedPython.PrintCollector import PrintCollector

from foundation import PermissionLevel

from registry import tool

_OPT_IN = "VRAKSHA_ENABLE_PYTHON_EXEC"

# RestrictedPython's safe_builtins omits many PURE, side-effect-free functions (sum, min, max,
# list, dict, set, enumerate, map, filter, ...), which left this tool unable to do even basic
# computation. Add ONLY harmless builtins back; NEVER add I/O, import, eval/exec/compile, open,
# or introspection escapes (those stay excluded, and attribute/item access stays guarded).
_SAFE_EXTRA = (
    "sum", "min", "max", "all", "any", "list", "dict", "set", "frozenset",
    "enumerate", "map", "filter", "reversed", "iter", "next", "bytearray",
    "format", "bin", "ascii",
)
_SAFE_BUILTINS = {
    **safe_globals["__builtins__"],
    **{n: getattr(_bi, n) for n in _SAFE_EXTRA if hasattr(_bi, n)},
}

import operator as _operator

# Augmented assignment (`x += 1`, `lst += [..]`, ...) compiles to a call to `_inplacevar_`;
# RestrictedPython provides no default, so supply a safe one over the standard in-place operators.
_INPLACE_OPS = {
    "+=": _operator.iadd, "-=": _operator.isub, "*=": _operator.imul,
    "/=": _operator.itruediv, "//=": _operator.ifloordiv, "%=": _operator.imod,
    "**=": _operator.ipow, "<<=": _operator.ilshift, ">>=": _operator.irshift,
    "&=": _operator.iand, "^=": _operator.ixor, "|=": _operator.ior,
}


def _inplacevar(op: str, var, expr):
    fn = _INPLACE_OPS.get(op)
    if fn is None:
        raise NotImplementedError(f"in-place operator {op!r} is not allowed")
    return fn(var, expr)


def _enabled() -> bool:
    return os.getenv(_OPT_IN, "").strip().lower() in {"1", "true", "yes"}


class PyExecIn(BaseModel):
    code: str


class PyExecOut(BaseModel):
    ok: bool
    output: str


@tool
class PythonExecTool:
    name = "python_exec"
    domain = "code"
    description = "Run a small snippet of restricted Python and return its printed output."
    input_schema = PyExecIn
    output_schema = PyExecOut
    permission = PermissionLevel.EXECUTE
    tags = ("sandbox", "compute")

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
        glb["__builtins__"] = _SAFE_BUILTINS       # safe compute builtins (sum/min/max/list/...)
        glb["_print_"] = PrintCollector
        glb["_getattr_"] = safer_getattr           # not raw getattr
        # iteration / subscript / unpack / write guards so for-loops, comprehensions, indexing,
        # and local assignment work (RestrictedPython inserts calls to these; missing -> NameError)
        glb["_getiter_"] = default_guarded_getiter
        glb["_getitem_"] = default_guarded_getitem
        glb["_write_"] = full_write_guard
        glb["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
        glb["_unpack_sequence_"] = guarded_unpack_sequence
        glb["_inplacevar_"] = _inplacevar          # augmented assignment (+=, -=, ...)
        local: dict = {}
        try:
            exec(byte_code, glb, local)
        except Exception as exc:
            return PyExecOut(ok=False, output=f"error: {exc}")

        printer = local.get("_print") or glb.get("_print")
        printed = printer() if callable(printer) else ""
        return PyExecOut(ok=True, output=str(printed).strip())
