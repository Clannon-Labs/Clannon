"""
Tests for demos/c6_consistency_demo.py.

The demo is a standalone script that invokes 4 contract/boundary checks and
renders a PASS/FAIL consistency table.  These tests verify:

  1. ``format_report`` produces well-formed output from synthetic SurfaceResults.
  2. The integration smoke test: ``main()`` exits 0 on the clean tree (the same
     baseline guarantee as TestBaselineGuard in test_check_invariants.py).

The integration test runs all 4 surfaces end-to-end so it is slower than the
unit tests, but it is the definitive proof that the demo is actually runnable
and that the existing drift-net checks still pass on the current HEAD.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the demo module from backend/scripts/.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from c6_consistency_demo import (  # noqa: E402
    InvariantRow,
    SurfaceResult,
    _parse_invariant_rows,
    format_report,
    main,
)


# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------

def _surface(pr: str, status: str, note: str = "2 tests passed",
             invariant_rows: list | None = None) -> SurfaceResult:
    return SurfaceResult(
        pr=pr,
        label=f"Surface {pr}",
        status=status,
        note=note,
        raw_output="",
        invariant_rows=invariant_rows or [],
    )


def _inv_rows_all_pass() -> list[InvariantRow]:
    return [
        InvariantRow("pydantic_ai confined to core/llm", "PASS", 0),
        InvariantRow("memory internals confined to core/memory", "PASS", 0, waived=2),
        InvariantRow("foundation imports nothing upward", "PASS", 0),
        InvariantRow("SET LOCAL not bare connection SET", "PASS", 0),
        InvariantRow("NETWORK tools route through SSRF gate", "WARN", 4),
        InvariantRow("no deep-import of foundation submodules", "PASS", 0),
    ]


# ---------------------------------------------------------------------------
# format_report unit tests
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_all_pass_verdict(self):
        surfaces = [
            _surface("#13", "PASS"),
            _surface("#21", "PASS"),
            _surface("#31", "PASS"),
            _surface("#32", "PASS", note="6 checks, 0 violations",
                     invariant_rows=_inv_rows_all_pass()),
        ]
        report = format_report(surfaces)
        assert "VERDICT: contracts held / boundaries intact" in report

    def test_fail_verdict_names_the_surface(self):
        surfaces = [
            _surface("#13", "PASS"),
            _surface("#21", "FAIL", note="1 failed"),
            _surface("#31", "PASS"),
            _surface("#32", "PASS", invariant_rows=_inv_rows_all_pass()),
        ]
        report = format_report(surfaces)
        assert "VERDICT: DIVERGENCE" in report
        assert "#21" in report

    def test_report_contains_all_pr_ids(self):
        surfaces = [
            _surface("#13", "PASS"),
            _surface("#21", "PASS"),
            _surface("#31", "PASS"),
            _surface("#32", "PASS", invariant_rows=_inv_rows_all_pass()),
        ]
        report = format_report(surfaces)
        for pr in ("#13", "#21", "#31", "#32"):
            assert pr in report

    def test_report_has_invariant_breakdown_section(self):
        surfaces = [
            _surface("#13", "PASS"),
            _surface("#21", "PASS"),
            _surface("#31", "PASS"),
            _surface("#32", "WARN", note="6 checks, 0 violations, 1 warning",
                     invariant_rows=_inv_rows_all_pass()),
        ]
        report = format_report(surfaces)
        assert "INVARIANT BREAKDOWN" in report
        assert "pydantic_ai confined to core/llm" in report

    def test_report_shows_waived_count(self):
        surfaces = [
            _surface("#32", "PASS", invariant_rows=_inv_rows_all_pass()),
        ]
        report = format_report(surfaces)
        assert "waived" in report  # warmup.py waived hits shown

    def test_report_shows_failure_detail_when_failing(self):
        surfaces = [
            _surface("#13", "FAIL", note="1 failed",
                     invariant_rows=[]),
        ]
        # Inject some fake raw output
        surfaces[0].raw_output = "FAILED tests/expert_contract.py::test_foo"
        report = format_report(surfaces)
        assert "FAILURE DETAIL" in report
        assert "FAILED" in report

    def test_report_no_failure_detail_when_all_pass(self):
        surfaces = [_surface("#13", "PASS")]
        report = format_report(surfaces)
        assert "FAILURE DETAIL" not in report

    def test_report_has_section_headers(self):
        surfaces = [_surface("#13", "PASS")]
        report = format_report(surfaces)
        assert "CONTRACT SURFACES" in report
        assert "VERDICT" in report
        assert "CLANNON C6" in report


# ---------------------------------------------------------------------------
# _parse_invariant_rows unit tests
# ---------------------------------------------------------------------------

class TestParseInvariantRows:
    _SAMPLE_OUTPUT = """\

Clannon invariant check — 92 file(s) scanned


  CHECK                                       STATUS  HITS
  ------------------------------------------  ------  ----
  pydantic_ai confined to core/llm            PASS    0
  memory internals confined to core/memory    PASS    0
  foundation imports nothing upward           PASS    0
  SET LOCAL not bare connection SET           PASS    0
  NETWORK tools route through SSRF gate       WARN    4
  no deep-import of foundation submodules     PASS    0

── memory internals confined to core/memory (§V.20 / §I.7) ──
   note: callers outside core/memory must use MemoryPort
   waived: backend/core/warmup.py:26  from core.memory import embeddings
   waived: backend/core/warmup.py:36  from core.memory import store

── NETWORK tools route through SSRF gate (§IV.17) ──
   note: WARNs use NETWORK permission but no direct HTTP client
   backend/experts/web_research/expert.py:0  PermissionLevel.NETWORK but no HTTP

RESULT: 5 PASS, 1 WARN — no hard violations detected
"""

    def test_parses_six_rows(self):
        rows = _parse_invariant_rows(self._SAMPLE_OUTPUT)
        assert len(rows) == 6

    def test_first_row_label_and_status(self):
        rows = _parse_invariant_rows(self._SAMPLE_OUTPUT)
        assert rows[0].label == "pydantic_ai confined to core/llm"
        assert rows[0].status == "PASS"
        assert rows[0].hits == 0

    def test_warn_row_parsed(self):
        rows = _parse_invariant_rows(self._SAMPLE_OUTPUT)
        warn = next(r for r in rows if r.status == "WARN")
        assert warn.label == "NETWORK tools route through SSRF gate"
        assert warn.hits == 4

    def test_waived_count_attached_to_memory_row(self):
        rows = _parse_invariant_rows(self._SAMPLE_OUTPUT)
        mem = next(r for r in rows if "memory" in r.label)
        assert mem.waived == 2

    def test_empty_output_returns_no_rows(self):
        assert _parse_invariant_rows("") == []

    def test_header_row_excluded(self):
        rows = _parse_invariant_rows(self._SAMPLE_OUTPUT)
        assert all(r.label.lower() != "check" for r in rows)


# ---------------------------------------------------------------------------
# Integration baseline — the demo must run clean on HEAD
# ---------------------------------------------------------------------------

class TestDemoBaseline:
    def test_main_exits_zero_on_clean_tree(self):
        """
        Run the full demo against the current HEAD and assert it exits 0.

        This is the definitive proof that:
          - all 4 drift-net checks pass on the clean tree (the same guarantee
            that check_invariants.py's TestBaselineGuard provides for #32 alone,
            but now across all 4 C6 surfaces), and
          - the demo runner itself is executable from the repo root without setup.
        """
        from unittest.mock import patch
        with patch.object(sys, "argv", ["c6_consistency_demo.py"]):
            exit_code = main()
        assert exit_code == 0, (
            "demo returned non-zero on clean tree: one or more C6 contract surfaces "
            "failed (see the report above)."
        )

    def test_demo_runnable_as_subprocess(self):
        """
        Verify the demo is runnable via ``python demos/c6_consistency_demo.py``
        from the repo root, which is the stated usage.  A non-zero exit code here
        means a real C6 contract divergence exists on HEAD.
        """
        repo = Path(__file__).resolve().parent.parent.parent
        venv_py = repo / "backend" / ".venv" / "bin" / "python"
        py = str(venv_py) if venv_py.exists() else sys.executable
        demo = str(repo / "backend" / "scripts" / "c6_consistency_demo.py")
        r = subprocess.run(
            [py, demo],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert r.returncode == 0, (
            f"demo exited {r.returncode}:\n{r.stdout[-2000:]}\n{r.stderr[-500:]}"
        )
        assert "VERDICT: contracts held / boundaries intact" in r.stdout
