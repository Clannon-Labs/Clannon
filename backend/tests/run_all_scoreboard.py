"""Tests for backend/scripts/benchmarks/run_all.py.

Verifies the scoreboard logic:
  - NOT-MEASURED when a harness module is absent or has no run() entry point
  - Correct verdict extracted when a harness exposes run() -> BenchmarkReport
  - E1 adapter works with the probe-style (_run_probe/_verdict) API
  - render() produces the expected section headers, summary, and gate line
  - main() always exits 0

All tests are hermetic (no real harness, no network, no DB).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load run_all module without polluting the packages namespace.
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parents[1] / "scripts" / "benchmarks" / "run_all.py"

_spec = importlib.util.spec_from_file_location("run_all", _SCRIPT)
run_all = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_all)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(overall_verdict: str, requirements=(), notes=()):
    """Construct a minimal mock BenchmarkReport."""
    report = MagicMock()
    overall_mock = MagicMock()
    overall_mock.value = overall_verdict
    report.overall.return_value = overall_mock
    report.requirements = list(requirements)
    report.notes = list(notes)
    return report


def _make_req(key, verdict_value, reason):
    req = MagicMock()
    req.verdict = MagicMock()
    req.verdict.value = verdict_value
    req.key = key
    req.reason = reason
    return req


# ---------------------------------------------------------------------------
# _run_standard
# ---------------------------------------------------------------------------

class TestRunStandard:
    def test_not_measured_when_module_missing(self):
        verdict, reason = run_all._run_standard("nonexistent_module_xyz")
        assert verdict == "NOT-MEASURED"
        assert "not yet landed" in reason

    def test_not_measured_when_no_run_attr(self):
        fake = types.ModuleType("benchmarks.no_run")
        with patch.dict(sys.modules, {"benchmarks.no_run": fake}):
            verdict, reason = run_all._run_standard("no_run")
        assert verdict == "NOT-MEASURED"
        assert "no run() entry point" in reason

    def test_correct_verdict_from_run(self):
        report = _make_report("PARTIAL")
        fake = types.ModuleType("benchmarks.fake_c5")
        fake.run = lambda: report
        with patch.dict(sys.modules, {"benchmarks.fake_c5": fake}):
            verdict, reason = run_all._run_standard("fake_c5")
        assert verdict == "PARTIAL"

    def test_fail_when_run_raises(self):
        fake = types.ModuleType("benchmarks.boom")
        fake.run = lambda: (_ for _ in ()).throw(RuntimeError("oops"))
        with patch.dict(sys.modules, {"benchmarks.boom": fake}):
            verdict, reason = run_all._run_standard("boom")
        assert verdict == "FAIL"
        assert "oops" in reason

    def test_reason_from_worst_requirement(self):
        reqs = [
            _make_req("detect", "PARTIAL", "semantic detection is live-only"),
            _make_req("prevent", "PASS", "pipeline halts on block"),
        ]
        report = _make_report("PARTIAL", requirements=reqs)
        fake = types.ModuleType("benchmarks.fake_reqs")
        fake.run = lambda: report
        with patch.dict(sys.modules, {"benchmarks.fake_reqs": fake}):
            _, reason = run_all._run_standard("fake_reqs")
        assert reason == "semantic detection is live-only"

    def test_reason_from_note_when_all_pass(self):
        reqs = [_make_req("a", "PASS", "ok")]
        report = _make_report("PASS", requirements=reqs, notes=["live model not certified here"])
        fake = types.ModuleType("benchmarks.fake_note")
        fake.run = lambda: report
        with patch.dict(sys.modules, {"benchmarks.fake_note": fake}):
            _, reason = run_all._run_standard("fake_note")
        assert "live model" in reason


# ---------------------------------------------------------------------------
# _run_e1 adapter
# ---------------------------------------------------------------------------

class TestRunE1:
    def test_not_measured_when_module_missing(self):
        # simulate absence — the real e1 harness HAS landed (PR #33), so the
        # missing-module path must be mocked, never assumed from the repo state
        with patch.object(run_all, "_import", return_value=None):
            verdict, reason = run_all._run_e1()
        assert verdict == "NOT-MEASURED"
        assert "not yet landed" in reason

    def test_uses_probe_api_when_no_run(self):
        package = MagicMock()
        package.items = [MagicMock(), MagicMock()]

        fake = types.ModuleType("benchmarks.e1_knowledge_evolution")
        fake._run_probe = lambda: package
        fake._verdict = lambda pkg: ("PARTIAL", ["no valid_until field (gated on #16)"])

        with patch.dict(sys.modules, {"benchmarks.e1_knowledge_evolution": fake}):
            verdict, reason = run_all._run_e1()

        assert verdict == "PARTIAL"
        assert "valid_until" in reason

    def test_defers_to_run_if_present(self):
        report = _make_report("PASS")
        report.requirements = []
        report.notes = ["all met"]

        fake = types.ModuleType("benchmarks.e1_knowledge_evolution")
        fake.run = lambda: report

        with patch.dict(sys.modules, {"benchmarks.e1_knowledge_evolution": fake}):
            verdict, _ = run_all._run_e1()

        assert verdict == "PASS"

    def test_not_measured_when_neither_api_present(self):
        fake = types.ModuleType("benchmarks.e1_knowledge_evolution")
        # No run(), no _run_probe, no _verdict
        with patch.dict(sys.modules, {"benchmarks.e1_knowledge_evolution": fake}):
            verdict, reason = run_all._run_e1()
        assert verdict == "NOT-MEASURED"
        assert "no run() or _run_probe" in reason

    def test_fail_when_probe_raises(self):
        fake = types.ModuleType("benchmarks.e1_knowledge_evolution")
        fake._run_probe = lambda: (_ for _ in ()).throw(RuntimeError("qdrant down"))
        fake._verdict = lambda p: ("PARTIAL", [])
        with patch.dict(sys.modules, {"benchmarks.e1_knowledge_evolution": fake}):
            verdict, reason = run_all._run_e1()
        assert verdict == "FAIL"
        assert "qdrant down" in reason


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------

class TestRender:
    def _all_not_measured(self):
        return [
            (bid, title, "NOT-MEASURED", "no harness")
            for bid, title, _ in run_all._BENCHMARKS
        ]

    def test_contains_section_headers(self):
        out = run_all.render(self._all_not_measured())
        assert "CRITICAL" in out
        assert "EXCEPTIONAL" in out

    def test_all_benchmark_ids_present(self):
        out = run_all.render(self._all_not_measured())
        for bid, _, _ in run_all._BENCHMARKS:
            assert bid in out

    def test_gate_not_met_when_all_not_measured(self):
        out = run_all.render(self._all_not_measured())
        assert "NOT MET" in out

    def test_gate_met_when_all_critical_and_one_exceptional_pass(self):
        results = []
        for bid, title, _ in run_all._BENCHMARKS:
            if bid.startswith("C"):
                results.append((bid, title, "PASS", "ok"))
            elif bid == "E1":
                results.append((bid, title, "PASS", "ok"))
            else:
                results.append((bid, title, "NOT-MEASURED", "no harness"))
        out = run_all.render(results)
        assert "Gate [MET]" in out

    def test_summary_counts(self):
        results = []
        for bid, title, _ in run_all._BENCHMARKS:
            results.append((bid, title, "PARTIAL", "gap"))
        out = run_all.render(results)
        assert f"{len(run_all._BENCHMARKS)} PARTIAL" in out

    def test_bar_delimiter_present(self):
        out = run_all.render(self._all_not_measured())
        assert "=" * 20 in out


# ---------------------------------------------------------------------------
# Benchmark registry completeness
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_nine_benchmarks_registered(self):
        assert len(run_all._BENCHMARKS) == 9

    def test_ids_are_c1_through_c6_and_e1_through_e3(self):
        ids = [b[0] for b in run_all._BENCHMARKS]
        assert ids == ["C1", "C2", "C3", "C4", "C5", "C6", "E1", "E2", "E3"]

    def test_c2_now_delegates_to_run_standard(self):
        """C2's thin-slice harness has landed (c2_repo_intelligence.py) — the
        registry entry moved from a static NOT-MEASURED placeholder to
        _run_standard, same as C1/C3/C4/C5/E2. Mocked, not asserted against the
        real harness's specific current verdict — this file's own convention
        (see TestRunE1 / test_e2_now_delegates_to_run_standard) is to test the
        WIRING here, not couple to one harness's scenario design."""
        report = _make_report("NOT-YET")
        fake = types.ModuleType("benchmarks.c2_repo_intelligence")
        fake.run = lambda: report
        c2 = next(b for b in run_all._BENCHMARKS if b[0] == "C2")
        with patch.dict(sys.modules, {"benchmarks.c2_repo_intelligence": fake}):
            verdict, _ = c2[2]()
        assert verdict == "NOT-YET"

    def test_c6_is_static_not_measured(self):
        # C6 is index 5
        c6 = next(b for b in run_all._BENCHMARKS if b[0] == "C6")
        verdict, reason = c6[2]()
        assert verdict == "NOT-MEASURED"

    def test_e2_now_delegates_to_run_standard(self):
        """E2's harness has landed (e2_project_continuity.py) — the registry entry
        moved from a static NOT-MEASURED placeholder to _run_standard, same as
        C1/C3/C4/C5. Mocked, not asserted against the real harness's specific
        current verdict: this file's own convention (see TestRunE1's "the real e1
        harness HAS landed... must be mocked, never assumed from the repo state")
        is to test the WIRING here, not couple to one harness's scenario design."""
        report = _make_report("PARTIAL")
        fake = types.ModuleType("benchmarks.e2_project_continuity")
        fake.run = lambda: report
        e2 = next(b for b in run_all._BENCHMARKS if b[0] == "E2")
        with patch.dict(sys.modules, {"benchmarks.e2_project_continuity": fake}):
            verdict, _ = e2[2]()
        assert verdict == "PARTIAL"

    def test_e3_is_static_not_measured(self):
        e3 = next(b for b in run_all._BENCHMARKS if b[0] == "E3")
        verdict, reason = e3[2]()
        assert verdict == "NOT-MEASURED"


# ---------------------------------------------------------------------------
# main() — always exits 0
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            run_all.main()
        assert exc_info.value.code == 0

    def test_main_prints_scoreboard(self, capsys):
        with pytest.raises(SystemExit):
            run_all.main()
        out = capsys.readouterr().out
        assert "CLANNON V1" in out
        assert "CRITICAL" in out
        assert "EXCEPTIONAL" in out
