"""
Tests for the chart visualization tool (viz.chart).

Acceptance matrix:
  (a) tool is discoverable through the registry with populated metadata
  (b) run() on valid bar and line inputs returns well-formed SVG containing
      the series labels deterministically
  (c) edge cases (empty / single-point / mismatched) return a structured
      safe result, never raise
"""

import asyncio

import pytest

from registry.capabilities import discover, registry
from tools.chart import ChartIn, ChartOut, ChartTool, Series


def _run(coro):
    return asyncio.run(coro)


# ─── (a) registry discovery ────────────────────────────────────────────────

def test_chart_tool_registered():
    discover()
    spec = registry.get_tool("viz.chart")
    assert spec is not None, "viz.chart not found in registry after discover()"


def test_chart_tool_not_broken():
    discover()
    broken_keys = {b.key for b in registry.broken()}
    assert "viz.chart" not in broken_keys


def test_chart_tool_metadata_populated():
    discover()
    spec = registry.get_tool("viz.chart")
    assert spec.description, "description must be non-empty"
    assert spec.input_schema is not None, "input_schema must be set"
    assert spec.output_schema is not None, "output_schema must be set"


def test_chart_tool_permission_read():
    from foundation import PermissionLevel
    discover()
    spec = registry.get_tool("viz.chart")
    assert spec.permission == PermissionLevel.READ


# ─── (b) valid inputs produce well-formed SVG ──────────────────────────────

def test_bar_chart_valid_two_series():
    result = _run(ChartTool().run(ChartIn(
        kind="bar",
        series=[
            Series(label="Revenue", values=[100.0, 200.0, 150.0]),
            Series(label="Cost",    values=[80.0,  120.0,  90.0]),
        ],
        title="Q1-Q3 Financials",
        x_label="Quarter",
        y_label="USD",
        x_labels=["Q1", "Q2", "Q3"],
    )))
    assert isinstance(result, ChartOut)
    assert result.error == "", f"unexpected error: {result.error}"
    assert result.content_type == "image/svg+xml"
    assert result.svg.startswith("<svg")
    assert result.svg.endswith("</svg>")
    assert "Revenue" in result.svg
    assert "Cost" in result.svg
    assert "Q1-Q3 Financials" in result.svg
    assert "Q1" in result.svg


def test_line_chart_valid_single_series():
    result = _run(ChartTool().run(ChartIn(
        kind="line",
        series=[Series(label="Temperature", values=[22.5, 24.1, 20.0, 19.3, 21.8])],
        title="Daily Temperature",
        x_labels=["Mon", "Tue", "Wed", "Thu", "Fri"],
    )))
    assert result.error == ""
    assert result.svg.startswith("<svg")
    assert result.svg.endswith("</svg>")
    assert "Temperature" in result.svg
    assert "Daily Temperature" in result.svg
    assert "Mon" in result.svg


def test_bar_chart_output_is_deterministic():
    args = ChartIn(
        kind="bar",
        series=[
            Series(label="A", values=[1.0, 2.0, 3.0]),
            Series(label="B", values=[3.0, 2.0, 1.0]),
        ],
    )
    r1 = _run(ChartTool().run(args))
    r2 = _run(ChartTool().run(args))
    assert r1.svg == r2.svg, "chart output must be byte-for-byte deterministic"


def test_line_chart_output_is_deterministic():
    args = ChartIn(
        kind="line",
        series=[
            Series(label="X", values=[1.0, 2.0, 3.0]),
            Series(label="Y", values=[3.0, 2.0, 1.0]),
        ],
    )
    r1 = _run(ChartTool().run(args))
    r2 = _run(ChartTool().run(args))
    assert r1.svg == r2.svg


# ─── (c) edge cases: safe result, never raise ──────────────────────────────

def test_empty_series_list_bar():
    result = _run(ChartTool().run(ChartIn(kind="bar", series=[])))
    assert isinstance(result, ChartOut)
    assert result.error == "no_data"
    assert result.svg.startswith("<svg")
    assert result.svg.endswith("</svg>")


def test_empty_series_list_line():
    result = _run(ChartTool().run(ChartIn(kind="line", series=[])))
    assert result.error == "no_data"
    assert result.svg.startswith("<svg")


def test_series_with_empty_values_treated_as_no_data():
    result = _run(ChartTool().run(ChartIn(
        kind="line",
        series=[Series(label="Empty", values=[])],
    )))
    assert result.error == "no_data"


def test_single_point_bar():
    result = _run(ChartTool().run(ChartIn(
        kind="bar",
        series=[Series(label="Metric", values=[42.0])],
    )))
    assert result.error == ""
    assert result.svg.startswith("<svg")
    assert result.svg.endswith("</svg>")
    assert "Metric" in result.svg


def test_single_point_line():
    result = _run(ChartTool().run(ChartIn(
        kind="line",
        series=[Series(label="Point", values=[7.5])],
    )))
    assert result.error == ""
    assert result.svg.startswith("<svg")
    assert "Point" in result.svg


def test_mismatched_series_lengths_truncates_to_shortest():
    result = _run(ChartTool().run(ChartIn(
        kind="bar",
        series=[
            Series(label="Long",  values=[1.0, 2.0, 3.0, 4.0, 5.0]),
            Series(label="Short", values=[10.0, 20.0]),
        ],
    )))
    assert result.error == "", "mismatched lengths should silently truncate, not error"
    assert result.svg.startswith("<svg")
    assert "Long" in result.svg
    assert "Short" in result.svg


def test_mismatched_x_labels_count_falls_back_gracefully():
    result = _run(ChartTool().run(ChartIn(
        kind="line",
        series=[Series(label="Data", values=[1.0, 2.0, 3.0])],
        x_labels=["Jan"],   # only 1 label for 3 data points
    )))
    assert result.error == ""
    assert result.svg.startswith("<svg")


def test_all_same_values_no_exception():
    result = _run(ChartTool().run(ChartIn(
        kind="bar",
        series=[Series(label="Flat", values=[5.0, 5.0, 5.0])],
    )))
    assert result.error == ""
    assert result.svg.startswith("<svg")


def test_negative_values_bar():
    result = _run(ChartTool().run(ChartIn(
        kind="bar",
        series=[Series(label="Profit/Loss", values=[-10.0, 5.0, -3.0, 8.0])],
    )))
    assert result.error == ""
    assert result.svg.startswith("<svg")
    assert "Profit/Loss" in result.svg


def test_no_network_filesystem_subprocess(monkeypatch):
    """Confirm run() does not import or call any network/fs/subprocess primitive."""
    import socket
    import subprocess
    import urllib.request

    calls: list[str] = []

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: calls.append("socket") or [])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append("subprocess"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: calls.append("urllib"))

    _run(ChartTool().run(ChartIn(
        kind="bar",
        series=[Series(label="Safe", values=[1.0, 2.0])],
    )))
    assert calls == [], f"run() made unexpected external calls: {calls}"
