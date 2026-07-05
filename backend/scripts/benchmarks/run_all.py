#!/usr/bin/env python
"""Consolidated V1 benchmark scoreboard.

Imports and runs every landed benchmark harness and prints a single
PASS / PARTIAL / FAIL / NOT-MEASURED table for Critical 1-6 and Exceptional
1-3, with a one-line reason per benchmark.

Harnesses live in backend/tests/benchmarks/ and are imported at runtime.
Any harness whose module cannot be imported (not yet landed) is reported as
NOT-MEASURED without aborting the run. This script is a reporting tool,
not a gate — it always exits 0.

Usage (from backend/):
    python scripts/benchmarks/run_all.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Ensure backend/ and backend/tests/ are on sys.path so both backend modules
# (e.g. core.memory) and the benchmarks package (tests/benchmarks/) resolve.
_BACKEND = Path(__file__).resolve().parents[2]
for _p in (_BACKEND, _BACKEND / "tests"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


# ---------------------------------------------------------------------------
# Harness import helper
# ---------------------------------------------------------------------------

def _import(module_name: str):
    """Import benchmarks.<module_name>; return the module or None on failure."""
    try:
        return importlib.import_module(f"benchmarks.{module_name}")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Verdict extraction helpers
# ---------------------------------------------------------------------------

_SEVERITY = {"PASS": 0, "NOT-MEASURED": 1, "NOT-YET": 2, "PARTIAL": 3, "FAIL": 4}


def _verdict_str(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _first_gap_reason(report) -> str:
    """Return the reason from the worst-verdict requirement, or the first note."""
    worst = None
    worst_sev = -1
    for r in report.requirements:
        sev = _SEVERITY.get(_verdict_str(r.verdict), 0)
        if sev > worst_sev:
            worst, worst_sev = r, sev
    if worst and _verdict_str(worst.verdict) != "PASS":
        return worst.reason
    if report.notes:
        return report.notes[0]
    return "all requirements met"


def _overall(report) -> str:
    return _verdict_str(report.overall())


# ---------------------------------------------------------------------------
# Per-harness runners
# ---------------------------------------------------------------------------

def _run_standard(module_name: str) -> tuple[str, str]:
    """Run a harness that exposes run() -> BenchmarkReport."""
    mod = _import(module_name)
    if mod is None:
        return "NOT-MEASURED", "harness not yet landed"
    if not hasattr(mod, "run"):
        return "NOT-MEASURED", f"{module_name} has no run() entry point"
    try:
        report = mod.run()
        return _overall(report), _first_gap_reason(report)
    except Exception as exc:
        return "FAIL", f"harness raised: {exc}"


def _run_e1() -> tuple[str, str]:
    """Adapter for E1 (Knowledge Evolution) which uses _run_probe()/_verdict().

    E1 pre-dates the run() -> BenchmarkReport convention; it exposes its own
    _run_probe() + _verdict() pair. If a future revision of e1_knowledge_evolution
    adds run(), this adapter transparently defers to it.
    """
    mod = _import("e1_knowledge_evolution")
    if mod is None:
        return "NOT-MEASURED", "harness not yet landed"
    if hasattr(mod, "run"):
        # Future-proof: respect run() if the harness is upgraded.
        try:
            report = mod.run()
            return _overall(report), _first_gap_reason(report)
        except Exception as exc:
            return "FAIL", f"harness raised: {exc}"
    # Probe-style API: _run_probe() -> HydrationPackage, _verdict(pkg) -> (str, list[str])
    if not (hasattr(mod, "_run_probe") and hasattr(mod, "_verdict")):
        return "NOT-MEASURED", "e1 module has no run() or _run_probe()/_verdict()"
    try:
        package = mod._run_probe()
        verdict_str, gaps = mod._verdict(package)
        reason = gaps[0] if gaps else f"{len(package.items)} items returned"
        return verdict_str, reason
    except Exception as exc:
        return "FAIL", f"probe raised: {exc}"


# ---------------------------------------------------------------------------
# Benchmark registry  (order: C1-C6, E1-E3)
# ---------------------------------------------------------------------------

_BENCHMARKS: list[tuple[str, str, object]] = [
    (
        "C1",
        "Persistent Cross-Session Memory",
        lambda: _run_standard("c1_memory"),
    ),
    (
        "C2",
        "Large Repository Understanding",
        lambda: (
            "NOT-MEASURED",
            "no harness; ADR 0008 PROPOSED, blocked on maintainer decision (issue #26)",
        ),
    ),
    (
        "C3",
        "Unified Multi-Modal Representation",
        lambda: _run_standard("c3_multimodal"),
    ),
    (
        "C4",
        "Institutional Decision Memory",
        lambda: _run_standard("c4_decision_memory"),
    ),
    (
        "C5",
        "Security Validation",
        lambda: _run_standard("c5_security"),
    ),
    (
        "C6",
        "Multi-Agent Architectural Consistency",
        lambda: (
            "NOT-MEASURED",
            "sse_contract_drift is a pytest gate (no run() BenchmarkReport), dedicated harness pending",
        ),
    ),
    (
        "E1",
        "Knowledge Evolution",
        _run_e1,
    ),
    (
        "E2",
        "Autonomous Project Continuity",
        lambda: _run_standard("e2_project_continuity"),
    ),
    (
        "E3",
        "Cross-Media Knowledge Synthesis",
        lambda: (
            "NOT-MEASURED",
            "no harness; ADR 0005 PROPOSED, gated on C3 convergence",
        ),
    ),
]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_BAR = "=" * 78
_ID_W = 4
_TITLE_W = 42
_VERDICT_W = 16


def _row(bid: str, title: str, verdict: str, reason: str) -> str:
    v = f"[{verdict}]"
    return f"  {bid:<{_ID_W}} {title:<{_TITLE_W}} {v:<{_VERDICT_W}} {reason}"


def render(results: list[tuple[str, str, str, str]]) -> str:
    """Render the scoreboard from [(id, title, verdict, reason)] rows."""
    lines = [
        _BAR,
        "CLANNON V1 ATTENTION THRESHOLD — DISTANCE-TO-PASS SCOREBOARD",
        _BAR,
        "",
        "CRITICAL (all 6 required to PASS before outreach)",
    ]
    for bid, title, verdict, reason in results:
        if bid.startswith("C"):
            lines.append(_row(bid, title, verdict, reason))

    lines += ["", "EXCEPTIONAL (>=1 required to PASS before outreach)"]
    for bid, title, verdict, reason in results:
        if bid.startswith("E"):
            lines.append(_row(bid, title, verdict, reason))

    lines.append("")

    verdicts = [v for _, _, v, _ in results]
    c_pass = sum(1 for b, _, v, _ in results if b.startswith("C") and v == "PASS")
    e_pass = sum(1 for b, _, v, _ in results if b.startswith("E") and v == "PASS")
    counts = {k: verdicts.count(k) for k in ("PASS", "PARTIAL", "FAIL", "NOT-YET", "NOT-MEASURED")}

    lines.append(
        f"Summary:  "
        f"{counts['PASS']} PASS  "
        f"{counts['PARTIAL']} PARTIAL  "
        f"{counts['FAIL']} FAIL  "
        f"{counts['NOT-YET']} NOT-YET  "
        f"{counts['NOT-MEASURED']} NOT-MEASURED"
    )
    gate_met = c_pass >= 6 and e_pass >= 1
    gate_label = "MET" if gate_met else "NOT MET"
    lines.append(
        f"Gate [{gate_label}]:  {c_pass}/6 Critical PASS  "
        f"{e_pass}/3 Exceptional PASS  "
        f"(need all 6 Critical + >=1 Exceptional)"
    )
    lines.append(_BAR)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    results = []
    for bid, title, runner in _BENCHMARKS:
        verdict, reason = runner()
        results.append((bid, title, verdict, reason))
    print(render(results))
    sys.exit(0)


if __name__ == "__main__":
    main()
