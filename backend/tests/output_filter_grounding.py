"""
Hermetic regression harness for the output filter's _grounding_view
content-assembly contract (security/filter/filter.py:41-86).

Pins the exact payload the filter LLM is shown when judging block-vs-pass,
which is the documented past-regression surface: "the filter was never shown
the findings - the regression that once blocked benign reports. Don't reintroduce
it." (security/filter/CLAUDE.md)

output_filter.py monkeypatches _filter ENTIRELY so _grounding_view is never
called; output_filter_retry.py pins the pipeline-level fail-closed retry loop.
This file exercises the grounding-view assembly function directly and optionally
the adjudication seam (run_structured patched, _filter called for real).

Run via pytest:
    cd backend && .venv/bin/python -m pytest tests/output_filter_grounding.py -v
Standalone contract table:
    cd backend && .venv/bin/python tests/output_filter_grounding.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

from foundation import Flow, NormalizedInput, OrchestratorResponse
import security.filter.filter as filter_stage
from security.filter.filter import (
    _grounding_view,
    _MAX_FINDINGS,
    _FINDING_CHARS,
    _MAX_TOOL_CALLS,
    _TOOL_RESULT_CHARS,
)
from security.filter.schemas import FilterResult


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

def _response(text="summary"):
    return SimpleNamespace(text=text)


def _finding(expert="web", content="x" * 2000, citations=None):
    return SimpleNamespace(
        expert=expert,
        full_content=content,
        citations=list(citations or []),
    )


def _tool(success=True, name="web_search", args=None, result="ok"):
    return SimpleNamespace(
        success=success,
        tool_name=name,
        arguments=args or {},
        result=result,
    )


def _memory(content="some memory content"):
    return SimpleNamespace(content=content)


def _view(response=None, findings=None, memory=None, tool_calls=None):
    """Call _grounding_view with in-memory doubles; json.loads the result."""
    return json.loads(
        _grounding_view(
            response or _response(),
            findings if findings is not None else [],
            memory if memory is not None else [],
            tool_calls if tool_calls is not None else [],
        )
    )


def _flow(text="hello"):
    flow = Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="q"), "s")
    flow.ctx.orchestrator_response = OrchestratorResponse(text=text, confidence=0.9)
    return flow


# ---------------------------------------------------------------------------
# DID-RESEARCH TOGGLE
# ---------------------------------------------------------------------------

def test_did_research_false_when_no_findings_and_no_tools():
    v = _view()
    assert v["did_research"] is False


def test_did_research_true_with_one_finding():
    v = _view(findings=[_finding()])
    assert v["did_research"] is True


def test_did_research_true_with_successful_tool_only():
    v = _view(tool_calls=[_tool(success=True)])
    assert v["did_research"] is True


# ---------------------------------------------------------------------------
# FAILED-TOOL EXCLUSION
# ---------------------------------------------------------------------------

def test_failed_tool_not_in_tool_results():
    v = _view(tool_calls=[_tool(success=False, name="web_search", result="err")])
    assert v["tool_results"] == []


def test_failed_tool_does_not_flip_did_research():
    v = _view(tool_calls=[_tool(success=False)])
    assert v["did_research"] is False


def test_mixed_tools_only_successful_included():
    v = _view(tool_calls=[
        _tool(success=False, name="bad"),
        _tool(success=True, name="good", result="found it"),
    ])
    assert len(v["tool_results"]) == 1
    assert v["tool_results"][0]["tool"] == "good"


# ---------------------------------------------------------------------------
# CONTENT INCLUSION + CAPS
# ---------------------------------------------------------------------------

def test_draft_appears_in_view():
    v = _view(response=_response("the report text"))
    assert v["draft"] == "the report text"


def test_finding_full_content_in_expert_findings():
    v = _view(findings=[_finding(content="short content", citations=["http://a.com"])])
    assert v["expert_findings"][0]["content"] == "short content"
    assert v["expert_findings"][0]["expert"] == "web"
    assert "http://a.com" in v["expert_findings"][0]["citations"]


def test_finding_content_truncated_at_finding_chars():
    long = "x" * (_FINDING_CHARS + 500)
    v = _view(findings=[_finding(content=long)])
    assert len(v["expert_findings"][0]["content"]) == _FINDING_CHARS


def test_findings_beyond_max_dropped():
    findings = [_finding(expert=f"e{i}") for i in range(_MAX_FINDINGS + 3)]
    v = _view(findings=findings)
    assert len(v["expert_findings"]) == _MAX_FINDINGS


def test_tool_calls_beyond_max_dropped():
    tools = [_tool(success=True, name=f"t{i}") for i in range(_MAX_TOOL_CALLS + 5)]
    v = _view(tool_calls=tools)
    assert len(v["tool_results"]) == _MAX_TOOL_CALLS


def test_tool_result_truncated_at_tool_result_chars():
    long_result = "y" * (_TOOL_RESULT_CHARS + 400)
    v = _view(tool_calls=[_tool(success=True, result=long_result)])
    assert len(v["tool_results"][0]["result"]) == _TOOL_RESULT_CHARS


def test_memory_content_truncated_at_300():
    long_mem = "m" * 500
    v = _view(memory=[_memory(content=long_mem)])
    assert len(v["memory_grounding"][0]) == 300


def test_memory_capped_at_10_items():
    mems = [_memory(content=f"item {i}") for i in range(15)]
    v = _view(memory=mems)
    assert len(v["memory_grounding"]) == 10


def test_sources_flattened_from_findings_and_capped_at_20():
    # 8 findings * 3 citations = 24 raw; capped to 20
    findings = [
        _finding(citations=[f"http://s{j}.com" for j in range(3)])
        for _ in range(_MAX_FINDINGS)
    ]
    v = _view(findings=findings)
    assert len(v["sources"]) == 20


# ---------------------------------------------------------------------------
# RECIPIENT STRING
# ---------------------------------------------------------------------------

def test_recipient_string_is_present():
    v = _view()
    assert v["recipient"] == "the same single authenticated user who made this request"


# ---------------------------------------------------------------------------
# PASS / BLOCK adjudication seam
# (monkeypatch run_structured so _filter is called for real, only the
#  LLM step is intercepted — distinct from output_filter.py which patches
#  _filter entirely and never exercises _grounding_view at all)
# ---------------------------------------------------------------------------

def test_pass_seam_run_structured_proceed_true(monkeypatch):
    fake_handle = object()
    monkeypatch.setattr(filter_stage, "build_agent", lambda *a, **kw: fake_handle)

    async def fake_run_structured(handle, prompt):
        return FilterResult(proceed=True)

    monkeypatch.setattr(filter_stage, "run_structured", fake_run_structured)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.status.value == "ok"
    assert out.ctx.filter_result.proceed is True
    assert out.ctx.filter_blocked is False


def test_block_seam_run_structured_proceed_false(monkeypatch):
    fake_handle = object()
    monkeypatch.setattr(filter_stage, "build_agent", lambda *a, **kw: fake_handle)

    async def fake_run_structured(handle, prompt):
        return FilterResult(proceed=False, blocked=True, reason="unsafe content")

    monkeypatch.setattr(filter_stage, "run_structured", fake_run_structured)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.status.value == "blocked"
    assert out.ctx.filter_blocked is True


# ---------------------------------------------------------------------------
# Standalone contract table
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import unittest.mock

    _BRANCHES: list[tuple[str, str, str]] = [
        ("DID-RESEARCH",        "no findings + no tools -> False",         "did_research_false_when_no_findings_and_no_tools"),
        ("DID-RESEARCH",        "finding present -> True",                 "did_research_true_with_one_finding"),
        ("DID-RESEARCH",        "successful tool only -> True",            "did_research_true_with_successful_tool_only"),
        ("FAILED-TOOL-EXCLUDED","not in tool_results",                     "failed_tool_not_in_tool_results"),
        ("FAILED-TOOL-EXCLUDED","does not flip did_research",              "failed_tool_does_not_flip_did_research"),
        ("FAILED-TOOL-EXCLUDED","mixed tools - only successful included",  "mixed_tools_only_successful_included"),
        ("CAPPED",              "draft in view",                           "draft_appears_in_view"),
        ("CAPPED",              "finding full_content included",           "finding_full_content_in_expert_findings"),
        ("CAPPED",              "finding content truncated at _FINDING_CHARS", "finding_content_truncated_at_finding_chars"),
        ("CAPPED",              "findings beyond _MAX_FINDINGS dropped",   "findings_beyond_max_dropped"),
        ("CAPPED",              "tool calls beyond _MAX_TOOL_CALLS dropped","tool_calls_beyond_max_dropped"),
        ("CAPPED",              "tool result truncated at _TOOL_RESULT_CHARS","tool_result_truncated_at_tool_result_chars"),
        ("CAPPED",              "memory content truncated at 300",         "memory_content_truncated_at_300"),
        ("CAPPED",              "memory capped at 10 items",               "memory_capped_at_10_items"),
        ("CAPPED",              "sources capped at 20",                    "sources_flattened_from_findings_and_capped_at_20"),
        ("RECIPIENT",           "fixed string present",                    "recipient_string_is_present"),
    ]

    results: dict[str, str] = {}
    any_violation = False

    for category, label, fn_name in _BRANCHES:
        fn = globals()[f"test_{fn_name}"]
        full_label = f"{category}: {label}"
        try:
            fn()
            results[full_label] = "HELD"
        except AssertionError as exc:
            results[full_label] = f"VIOLATED ({exc})"
            any_violation = True
        except Exception as exc:
            results[full_label] = f"ERROR ({exc})"
            any_violation = True

    # PASS / BLOCK seam via unittest.mock (no pytest fixture in standalone mode)
    for label, proceed, expected_status in [
        ("PASS: proceed=True -> status ok",       True,  "ok"),
        ("BLOCK: proceed=False -> status blocked", False, "blocked"),
    ]:
        try:
            _proceed = proceed
            async def _fake_run(_h, _p, _proceed=_proceed):
                return FilterResult(proceed=_proceed)
            _fake_handle = object()
            with (
                unittest.mock.patch.object(filter_stage, "build_agent", return_value=_fake_handle),
                unittest.mock.patch.object(filter_stage, "run_structured", _fake_run),
            ):
                out = asyncio.run(filter_stage.run(_flow()))
            assert out.status.value == expected_status
            results[label] = "HELD"
        except Exception as exc:
            results[label] = f"VIOLATED ({exc})"
            any_violation = True

    COL_CAT = 22
    COL_LBL = 48
    print()
    print("output-filter _grounding_view contract")
    print("=" * (COL_CAT + COL_LBL + 12))
    for full_label, status in results.items():
        cat, _, rest = full_label.partition(": ")
        print(f"  {cat:<{COL_CAT}} {rest:<{COL_LBL}} {status}")
    print("=" * (COL_CAT + COL_LBL + 12))
    verdict = "VIOLATED" if any_violation else "grounding-view contract held"
    print(f"  verdict: {verdict}")
    print()

    if any_violation:
        print("NOTE: any VIOLATED branch is a divergence from the documented contract.")
        print("Flag for needs-reviewer before merging a filter change that causes this.")
        print()

    sys.exit(1 if any_violation else 0)
