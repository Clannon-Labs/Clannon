"""diff tool (key: text.diff) — pure stdlib line diff, no external deps."""

from __future__ import annotations

import difflib
from typing import Literal

from pydantic import BaseModel

from foundation import PermissionLevel
from registry import tool

# Combined-input guard: difflib's matcher is ~O(n·m), so a hard char cap keeps a
# pathological pair from pinning the tool timeout. Upstream text is already bounded
# (sanitizer caps at 100k chars); this is defence in depth, and honest when it trips.
_MAX_CHARS = 200_000


# ─── change accounting ──────────────────────────────────────────────────────

def _count_changes(a_lines: list[str], b_lines: list[str]) -> tuple[int, int]:
    """Added/removed line counts, computed from the edit opcodes so the numbers are
    the same regardless of which render `format` was requested. `replace` counts as
    both a removal (of the old lines) and an addition (of the new)."""
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    added = removed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            removed += i2 - i1
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "insert":
            added += j2 - j1
    return added, removed


# ─── schema ─────────────────────────────────────────────────────────────────

class DiffIn(BaseModel):
    a: str = ""                                      # original / left text
    b: str = ""                                      # modified / right text
    a_label: str = "a"                               # header label for the left side
    b_label: str = "b"                               # header label for the right side
    context_lines: int = 3                           # lines of surrounding context (unified/context)
    format: Literal["unified", "context", "ndiff"] = "unified"


class DiffOut(BaseModel):
    diff: str = ""                                   # rendered diff ("" when the two are line-identical)
    added: int = 0                                   # lines present in b but not a
    removed: int = 0                                 # lines present in a but not b
    changed: bool = False                            # whether the two texts differ at line level
    content_type: str = "text/x-diff"
    error: str = ""


# ─── tool ───────────────────────────────────────────────────────────────────

@tool
class DiffTool:
    name = "diff"
    domain = "text"
    description = (
        "Computes a line-level diff between two texts — unified (default), context, or "
        "ndiff format — with added/removed line counts and a `changed` flag. Deterministic, "
        "pure-stdlib; use it to compare document or code revisions. Compares by line, so a "
        "difference only in the trailing newline reads as identical."
    )
    input_schema = DiffIn
    output_schema = DiffOut
    permission = PermissionLevel.READ
    tags = ("text", "diff", "compare")

    async def run(self, args: DiffIn) -> DiffOut:
        try:
            if len(args.a) + len(args.b) > _MAX_CHARS:
                return DiffOut(error="inputs_too_large")

            a_lines = args.a.splitlines()
            b_lines = args.b.splitlines()
            if a_lines == b_lines:
                return DiffOut(changed=False)          # line-identical → nothing to diff

            n = max(args.context_lines, 0)
            if args.format == "ndiff":
                lines = list(difflib.ndiff(a_lines, b_lines))
            elif args.format == "context":
                lines = list(difflib.context_diff(
                    a_lines, b_lines, fromfile=args.a_label, tofile=args.b_label, n=n, lineterm=""))
            else:  # unified
                lines = list(difflib.unified_diff(
                    a_lines, b_lines, fromfile=args.a_label, tofile=args.b_label, n=n, lineterm=""))

            added, removed = _count_changes(a_lines, b_lines)
            return DiffOut(diff="\n".join(lines), added=added, removed=removed, changed=True)
        except Exception as exc:  # noqa: BLE001 — a diff fault returns a structured error, never raises
            return DiffOut(error=str(exc))
