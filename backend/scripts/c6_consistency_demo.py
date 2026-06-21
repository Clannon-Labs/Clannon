#!/usr/bin/env python3
"""
backend/scripts/c6_consistency_demo.py

C6 multi-agent architectural-consistency demo scene.

Invokes the four independently-authored contract + boundary checks that form the
C6 drift-net and renders their results as one human-readable PASS/FAIL consistency
report — the "agent organisation stayed coherent" snapshot for Clannon's outreach demo.

Checks invoked (additive tests and scripts, none modified here):
  #13  backend/tests/expert_contract.py
       Shared expert run() entry-point: every expert exposes the same
       ``async def run(self, args: <input_schema>, env: ExpertEnv) -> ExpertOutput``.

  #21  backend/tests/registration_drift.py
       @tool/@expert spec-mirroring: the decorator copies every capability
       class attribute onto ToolSpec/ExpertSpec without drift.

  #31  backend/tests/benchmarks/sse_contract_drift.py
       SSE frontend/backend contract drift: event names, payload shapes, and
       enum vocabularies the frontend expects must match what the backend emits.

  #32  backend/scripts/check_invariants.py
       Invariant boundary checks: pydantic_ai confined to core/llm, memory
       internals confined to core/memory, foundation dep direction, SET LOCAL
       (not bare SET), NETWORK/SSRF gate, no deep foundation submodule imports.

The script invokes each check as a subprocess, parses the results, and prints:
  1. A per-surface PASS/FAIL table with test/check counts.
  2. A per-invariant PASS/FAIL/WARN breakdown from check_invariants.py (#32).
  3. A one-line verdict: "contracts held / boundaries intact" or a list of
     divergent surfaces.

On divergence the report identifies the failure without editing either side;
reconciliation is a maintainer decision per the C6 drift policy.

Usage (from repo root):
    python demos/c6_consistency_demo.py

Exit code:
    0  all surfaces PASS (or at most WARN)
    1  one or more surfaces FAIL (divergence reported, neither side edited)
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent  # backend/
_REPO = _BACKEND.parent                             # repo root
_VENV_PY = _BACKEND / ".venv" / "bin" / "python"
_PY = str(_VENV_PY) if _VENV_PY.exists() else sys.executable

_REPORT_WIDTH = 72


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class InvariantRow:
    label: str
    status: str  # PASS | FAIL | WARN
    hits: int
    waived: int = 0


@dataclass
class SurfaceResult:
    pr: str
    label: str
    status: str  # PASS | FAIL | WARN | ERROR
    note: str
    raw_output: str
    invariant_rows: list[InvariantRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _run_pytest(rel: str) -> SurfaceResult:
    """Run a pytest module relative to the backend dir; return a SurfaceResult."""
    # surface label and PR come from the caller
    path = _BACKEND / rel
    if not path.exists():
        return SurfaceResult(
            pr="", label="", status="ERROR",
            note=f"file not found: {path}",
            raw_output=f"missing: {path}",
        )
    try:
        r = subprocess.run(
            [_PY, "-m", "pytest", str(path),
             "-q", "-p", "no:cacheprovider",
             "--tb=line", "--no-header", "--color=no"],
            cwd=str(_BACKEND),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return SurfaceResult(
            pr="", label="", status="ERROR",
            note="timed out (120s)", raw_output="",
        )

    output = r.stdout + r.stderr
    passed = sum(int(m) for m in re.findall(r"(\d+) passed", output))
    failed = sum(int(m) for m in re.findall(r"(\d+) failed", output))
    skipped = sum(int(m) for m in re.findall(r"(\d+) skipped", output))

    if r.returncode == 0:
        status = "PASS"
    elif failed:
        status = "FAIL"
    else:
        status = "ERROR"

    parts: list[str] = []
    if passed:
        parts.append(f"{passed} test{'s' if passed != 1 else ''} passed")
    if skipped:
        parts.append(f"{skipped} skipped")
    if failed:
        parts.append(f"{failed} failed")
    note = ", ".join(parts) if parts else "no tests collected"

    return SurfaceResult(pr="", label="", status=status, note=note, raw_output=output)


def _parse_invariant_rows(output: str) -> list[InvariantRow]:
    """Parse the check_invariants table and waived counts from script output."""
    rows: list[InvariantRow] = []
    waived: dict[str, int] = {}
    current_section: str | None = None

    for line in output.splitlines():
        # Table data row: "  label<spaces>PASS|FAIL|WARN<spaces>N"
        tm = re.match(r"  (.+?)\s{2,}(PASS|FAIL|WARN)\s+(\d+)\s*$", line)
        if tm:
            label = tm.group(1).strip()
            if label.lower() == "check":
                continue
            rows.append(InvariantRow(label=label, status=tm.group(2), hits=int(tm.group(3))))
            continue
        # Detail section header: "── label (ref) ──"
        hm = re.match(r"^── (.+?) \(", line)
        if hm:
            current_section = hm.group(1).strip()
            continue
        # Waived line in detail section
        if current_section and re.match(r"\s+waived:", line):
            waived[current_section] = waived.get(current_section, 0) + 1

    for row in rows:
        row.waived = waived.get(row.label, 0)

    return rows


def _run_invariants() -> SurfaceResult:
    """Run check_invariants.py; return a SurfaceResult with invariant_rows."""
    script = _BACKEND / "scripts" / "check_invariants.py"
    if not script.exists():
        return SurfaceResult(
            pr="#32", label="Invariant checks", status="ERROR",
            note=f"script not found: {script}", raw_output="",
        )
    try:
        r = subprocess.run(
            [_PY, str(script)],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return SurfaceResult(
            pr="#32", label="Invariant checks", status="ERROR",
            note="timed out (60s)", raw_output="",
        )

    output = r.stdout + r.stderr
    inv_rows = _parse_invariant_rows(output)

    n = len(inv_rows)
    violations = sum(row.hits for row in inv_rows if row.status == "FAIL")
    warns = sum(1 for row in inv_rows if row.status == "WARN")

    status = "FAIL" if r.returncode != 0 else ("WARN" if warns else "PASS")
    note_parts = [f"{n} check{'s' if n != 1 else ''}"]
    if violations:
        note_parts.append(f"{violations} violation{'s' if violations != 1 else ''}")
    else:
        note_parts.append("0 violations")
    if warns:
        note_parts.append(f"{warns} warning{'s' if warns != 1 else ''}")

    return SurfaceResult(
        pr="#32",
        label="Invariant checks (user_id / Flow / SET LOCAL / SDK)",
        status=status,
        note=", ".join(note_parts),
        raw_output=output,
        invariant_rows=inv_rows,
    )


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

_PYTEST_SURFACES = [
    ("#13", "Expert run() entry-point contract",
     "tests/expert_contract.py"),
    ("#21", "@tool/@expert spec-mirroring",
     "tests/registration_drift.py"),
    ("#31", "SSE frontend/backend event drift",
     "tests/benchmarks/sse_contract_drift.py"),
]


def run_demo() -> list[SurfaceResult]:
    """Invoke all 4 surfaces and return their results."""
    results: list[SurfaceResult] = []

    for pr, label, rel in _PYTEST_SURFACES:
        sr = _run_pytest(rel)
        sr.pr = pr
        sr.label = label
        results.append(sr)

    results.append(_run_invariants())
    return results


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def format_report(surfaces: list[SurfaceResult]) -> str:
    """Format a human-readable per-surface + per-invariant PASS/FAIL report."""
    W = _REPORT_WIDTH
    lines: list[str] = []

    lines.append("=" * W)
    lines.append("  CLANNON C6 — MULTI-AGENT ARCHITECTURAL CONSISTENCY")
    lines.append("=" * W)
    lines.append("")

    # --- surface table ---
    lines.append("CONTRACT SURFACES")
    col = max(len(f"{s.pr}  {s.label}") for s in surfaces) + 2
    lines.append(f"  {'─' * col}  {'─' * 6}  {'─' * 27}")
    for s in surfaces:
        lbl = f"{s.pr}  {s.label}"
        lines.append(f"  {lbl:<{col}}  {s.status:<6}  {s.note}")
    lines.append("")

    # --- invariant breakdown from #32 ---
    inv = next((s for s in surfaces if s.pr == "#32"), None)
    if inv and inv.invariant_rows:
        lines.append("INVARIANT BREAKDOWN  (backend/scripts/check_invariants.py)")
        icol = max(len(r.label) for r in inv.invariant_rows) + 2
        lines.append(f"  {'─' * icol}  {'─' * 6}  {'─' * 27}")
        for row in inv.invariant_rows:
            hit_note = f"{row.hits} violation{'s' if row.hits != 1 else ''}"
            if row.waived:
                hit_note += f" ({row.waived} waived)"
            lines.append(f"  {row.label:<{icol}}  {row.status:<6}  {hit_note}")
        lines.append("")

    # --- failure detail (raw output, last 40 lines per surface) ---
    failing = [s for s in surfaces if s.status in ("FAIL", "ERROR")]
    if failing:
        lines.append("FAILURE DETAIL")
        lines.append("─" * W)
        for s in failing:
            lines.append(f"[{s.pr}] {s.label}")
            tail = s.raw_output.strip().splitlines()
            for ln in tail[-40:]:
                lines.append(f"  {ln}")
            lines.append("")

    # --- verdict ---
    lines.append("─" * W)
    if failing:
        names = "  |  ".join(f"{s.pr} {s.label}" for s in failing)
        lines.append(f"VERDICT: DIVERGENCE — {names}")
        lines.append(
            "  (neither side was edited; reconciliation is a maintainer decision)"
        )
    else:
        lines.append("VERDICT: contracts held / boundaries intact")
    lines.append("=" * W)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    print("\nRunning C6 multi-agent consistency checks...\n", flush=True)
    surfaces = run_demo()
    print(format_report(surfaces))
    return 1 if any(s.status in ("FAIL", "ERROR") for s in surfaces) else 0


if __name__ == "__main__":
    sys.exit(main())
