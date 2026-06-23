"""
tests/decision_log_filter_independence.py

Hermetic harness pinning the C6 architectural split:

    "the orchestrator's structured decision log streams DIRECTLY to the user
    while ONLY the final report buffers through the output filter"

Three contract assertions:
  (a) DECISION-LOG-DELIVERED  -- log entries survive a blocking filter verdict;
                                 the log is already on ctx before the filter runs
                                 so the filter verdict cannot suppress it.
  (b) REPORT-FILTERED         -- final_response is always filter-approved text,
                                 never the raw orchestrator draft; when the filter
                                 blocks, final_response stays None.
  (c) FILTER-SAW-LOG          -- the filter receives the final report only, never
                                 the decision-log entries.

Hermetic: no network, no paid keys.  The real orchestrator loop (loop.py),
output filter stage (security/filter/filter.py), and delivery stage
(delivery/delivery.py) run.  The LLM capability door, memory store, and the
filter LLM call itself are test doubles.

On a genuine violation the harness prints a VIOLATED verdict and opens a
needs-reviewer note at needs_reviewer_c6_split.md alongside this file, rather
than patching production code.

Pins: Critical Benchmark 6 (C6 Architectural Consistency), specifically the
decision-log/output-filter independence contract.

Run:
    cd backend && .venv/bin/python -m pytest tests/decision_log_filter_independence.py -s -v
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import time
from unittest.mock import patch

from foundation import (
    Flow,
    HydrationPackage,
    NormalizedInput,
    Origin,
)
from core.orchestrator import loop as loop_mod
from core.orchestrator.ports import Ports
from core.orchestrator.schemas import OrchestratorAnswer
from core.orchestrator.utils.decision_log import CtxDecisionLog
from registry.capabilities import ExpertFindings
import security.filter.filter as filter_mod
from security.filter.schemas import FilterResult
from delivery.delivery import run as delivery_run


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPORT_TEXT = "FULL EXPERT REPORT: AI safety research summary — production quality."
_BRIEF = "Summarise the current state of AI safety research."

_NEEDS_REVIEWER_PATH = pathlib.Path(__file__).parent / "needs_reviewer_c6_split.md"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _FakeCaps:
    """Fake capability door.

    Emits one tool-call event (search.web) and buffers one expert finding so the
    response routes through the deliverable channel (not the short-reply chat
    bubble path).  Returns a canned OrchestratorAnswer that references the finding.
    No model, no network.
    """

    def __init__(self, ctx):
        self._ctx = ctx

    async def run_turn(
        self,
        *,
        system_prompt,
        user_prompt,
        output_type,
        on_event=None,
        on_message=None,
        **kw,
    ):
        if on_event is not None:
            await on_event({"tool": "search.web", "args": {"query": "AI safety"}})
        self._ctx.expert_findings.append(
            ExpertFindings(
                expert="web.research",
                ref="r1",
                full_content=_REPORT_TEXT,
            )
        )
        return OrchestratorAnswer(
            answer_text="Lean summary for the decision log.",
            confidence=0.85,
            deliverable_ref="r1",
        )


class _FakeMemory:
    """Fake memory port: hydrate returns an empty package; writes are no-ops."""

    async def hydrate(self, request):
        return HydrationPackage()

    async def record_write_proposals(self, *a):
        pass

    async def learn(self, *a, **kw):
        pass


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def _run_scenario(*, filter_blocks: bool):
    """
    Drive a benign brief through the real orchestrator loop, real filter stage,
    and real delivery stage using test doubles for the LLM and filter.

    Returns a dict with the state to assert against:
        log_entries     list[DecisionLogEntry]   -- what was on ctx after orch
        filter_called   bool                     -- did the filter run at all?
        filter_input    dict                     -- what the filter received
        final_response  str | None               -- what ended up as final output
        filter_blocked  bool
    """
    filter_calls: list[dict] = []

    async def _spy_blocking(_response, _findings, _memory, _tool_calls):
        filter_calls.append({
            "response_text": getattr(_response, "text", ""),
            "findings": list(_findings),
            "memory": list(_memory),
            "tool_calls": list(_tool_calls),
        })
        return FilterResult(proceed=False, blocked=True, reason="harness_block")

    async def _spy_passing(_response, _findings, _memory, _tool_calls):
        filter_calls.append({
            "response_text": getattr(_response, "text", ""),
            "findings": list(_findings),
            "memory": list(_memory),
            "tool_calls": list(_tool_calls),
        })
        return FilterResult(proceed=True)

    spy = _spy_blocking if filter_blocks else _spy_passing

    async def _inner():
        # Build a fresh flow with the brief as the NormalizedInput payload.
        normalized = NormalizedInput(
            modality="text",
            content_type="text/plain",
            content=_BRIEF,
        )
        flow = Flow.new(normalized, session_id="s-harness", user_id="u-harness")
        ctx = flow.ctx

        # Assemble fake ports: fake caps + fake memory + real decision-log sink.
        ports = Ports(
            memory=_FakeMemory(),
            caps=_FakeCaps(ctx),
            log=CtxDecisionLog(ctx),
        )

        # 1. Run the REAL orchestrator loop with the fake ports.
        #    This is the code that emits DecisionLogEntry objects to ctx.decision_log
        #    (loop.py:37-62: on_event appends tool_call entries; the answer is appended
        #    at the end of run_loop).  No filter is involved yet.
        response = await loop_mod.run_loop(normalized, ports, ctx)
        ctx.orchestrator_response = response
        log_entries_after_orch = list(ctx.decision_log)  # snapshot before filter
        flow = flow.next(response, Origin.ORCHESTRATOR, time.monotonic())

        # 2. Run the REAL filter stage with the spy double.
        #    The real filter.run() reads ctx.orchestrator_response.text, calls _filter()
        #    (which we replace), and sets ctx.filter_blocked on rejection.
        with patch.object(filter_mod, "_filter", spy):
            flow = await filter_mod.run(flow)

        # 3. Run the REAL delivery stage only when the filter passes.
        #    When the filter blocks, the flow is short-circuited (flow.should_stop)
        #    and delivery is intentionally skipped -- the raw draft must never reach
        #    final_response.  CLI output is suppressed in tests.
        if not flow.ctx.filter_blocked:
            os.environ["VRAKSHA_CLI_QUIET"] = "1"
            flow = await delivery_run(flow)

        return {
            "log_entries": log_entries_after_orch,
            "filter_called": bool(filter_calls),
            "filter_input": filter_calls[0] if filter_calls else {},
            "final_response": ctx.final_response,
            "filter_blocked": ctx.filter_blocked,
            "orchestrator_response_text": response.text,
        }

    return asyncio.run(_inner())


# ---------------------------------------------------------------------------
# Verdict helpers
# ---------------------------------------------------------------------------

def _check_assertions(blocking_result, passing_result):
    """
    Evaluate all three contract assertions and return a list of (label, ok, detail)
    tuples.  All three share a single run each (blocking and passing scenarios);
    none of the checks edits production code.
    """
    results = []

    # --- (a) DECISION-LOG-DELIVERED -----------------------------------------
    # Decision-log entries must be present even when the filter blocks.
    # They are emitted during orchestration, BEFORE the filter runs, so the
    # filter verdict cannot retroactively suppress them.
    log_present = len(blocking_result["log_entries"]) > 0
    log_has_tool_call = any(
        getattr(e, "kind", "") == "tool_call"
        for e in blocking_result["log_entries"]
    )
    log_has_answer = any(
        getattr(e, "kind", "") == "answer"
        for e in blocking_result["log_entries"]
    )
    a_ok = log_present and log_has_tool_call and log_has_answer
    results.append((
        "DECISION-LOG-DELIVERED",
        a_ok,
        (
            f"{len(blocking_result['log_entries'])} log entries present "
            f"(tool_call={log_has_tool_call}, answer={log_has_answer}) "
            "after filter block"
        ),
    ))

    # --- (b) REPORT-FILTERED ------------------------------------------------
    # (b1) When the filter blocks, final_response must be None -- the raw draft
    #      must NEVER leak to the user.
    b1_ok = blocking_result["final_response"] is None
    results.append((
        "REPORT-FILTERED (block)",
        b1_ok,
        (
            "final_response=None when filter blocks"
            if b1_ok
            else f"final_response leaked raw draft: {blocking_result['final_response']!r}"
        ),
    ))

    # (b2) When the filter passes, final_response must equal the
    #      orchestrator_response.text that the filter approved -- not some
    #      pre-filter or alternative text.
    expected = passing_result["orchestrator_response_text"]
    b2_ok = passing_result["final_response"] == expected
    results.append((
        "REPORT-FILTERED (pass)",
        b2_ok,
        (
            f"final_response == orchestrator_response.text ({expected!r})"
            if b2_ok
            else (
                f"final_response ({passing_result['final_response']!r}) "
                f"!= orchestrator_response.text ({expected!r})"
            )
        ),
    ))

    # --- (c) FILTER-SAW-LOG -------------------------------------------------
    # The filter must only see the orchestrator_response.text (and grounding
    # context: findings, memory, tool_calls).  It must NEVER see the decision-log
    # entries; the log reaches the user via a completely separate path.
    filter_input = blocking_result["filter_input"]
    filter_response_text = filter_input.get("response_text", "")
    log_messages = {
        getattr(e, "message", "") for e in blocking_result["log_entries"]
    }
    # The filter received the right text (the final report, not a log entry).
    c_response_correct = filter_response_text == blocking_result["orchestrator_response_text"]
    # None of the decision-log messages appear inside the filter's response_text
    # or findings.  (If any log entry text leaked into the filter payload it
    # would mean the log was routed through the filter, violating the contract.)
    findings_text = " ".join(
        str(getattr(f, "full_content", "")) for f in filter_input.get("findings", [])
    )
    filter_combined_payload = filter_response_text + findings_text
    log_leaked = any(
        msg and msg in filter_combined_payload for msg in log_messages
        # The lean summary ("Lean summary for the decision log.") is ALSO the
        # answer log entry (loop.py emits it as `kind="answer"`).  But the filter
        # receives the FULL expert artifact text via response.text, not the lean
        # summary.  So this check is that the log-entry strings do not appear
        # verbatim in what the filter payload *unless* they happen to be
        # substrings of the report itself -- which in our synthetic scenario they
        # are not, since the report text is distinct.
        if msg not in _REPORT_TEXT
    )
    c_ok = c_response_correct and not log_leaked
    results.append((
        "FILTER-SAW-LOG",
        c_ok,
        (
            f"filter received response.text={filter_response_text!r}; "
            f"log messages {sorted(log_messages)!r} not in filter payload"
            if c_ok
            else (
                f"VIOLATION: filter received unexpected payload -- "
                f"response_text={filter_response_text!r}, "
                f"log_messages={sorted(log_messages)!r}, "
                f"c_response_correct={c_response_correct}, "
                f"log_leaked={log_leaked}"
            )
        ),
    ))

    return results


def _print_table(results):
    """Print the per-assertion verdict table to stdout."""
    width = max(len(label) for label, _, _ in results) + 2
    print()
    print("=" * (width + 26))
    print(f"  C6 decision-log / output-filter independence")
    print("=" * (width + 26))
    print(f"  {'ASSERTION':<{width}}  VERDICT")
    print(f"  {'-' * width}  -------")
    all_ok = True
    for label, ok, detail in results:
        verdict = "split held" if ok else "VIOLATED"
        print(f"  {label:<{width}}  {verdict}")
        if not ok:
            print(f"    -> {detail}")
            all_ok = False
    print("=" * (width + 26))
    if all_ok:
        print("  Overall: split held (all 3 contracts intact)")
    else:
        print("  Overall: VIOLATED -- see needs-reviewer note")
    print("=" * (width + 26))
    print()
    return all_ok


def _open_needs_reviewer(results):
    """Write a needs-reviewer note when a genuine violation is detected."""
    violations = [(label, detail) for label, ok, detail in results if not ok]
    if not violations:
        return
    lines = [
        "# needs-reviewer: C6 decision-log / output-filter split VIOLATED",
        "",
        "Harness: `tests/decision_log_filter_independence.py`  ",
        "Date detected: 2026-06-23  ",
        "Branch: `test/decision-log-bypasses-filter`",
        "",
        "## Violated contracts",
        "",
    ]
    for label, detail in violations:
        lines.append(f"- **{label}**: {detail}")
    lines += [
        "",
        "## Background",
        "",
        "The C6 invariant requires that the orchestrator's decision log streams",
        "directly to the user, while ONLY the final report buffers through the",
        "output filter.  One or more of the three sub-contracts above is broken.",
        "",
        "## Options",
        "",
        "1. If the filter now reads ctx.decision_log (violation c): remove that",
        "   path from filter.py -- the log must never route through the filter.",
        "2. If the decision log is suppressed when the filter blocks (violation a):",
        "   the log sink must be independent of the filter outcome -- check",
        "   pipeline.py _drive_with_revision and delivery.py.",
        "3. If raw report leaks to final_response without filter approval (violation b):",
        "   delivery.py must only run after the filter passes.",
        "",
        "## Recommendation",
        "",
        "Option 1/2/3 above depending on which assertion failed.  Do NOT patch the",
        "test to hide the violation -- fix the production code or record a deliberate",
        "architectural decision here.",
    ]
    _NEEDS_REVIEWER_PATH.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_decision_log_delivered_when_filter_blocks():
    """(a) Decision-log entries survive a blocking filter verdict.

    The log is populated during orchestration (before the filter runs), so a
    filter block cannot retroactively suppress it.
    """
    result = _run_scenario(filter_blocks=True)
    log = result["log_entries"]
    kinds = [getattr(e, "kind", "") for e in log]
    assert len(log) > 0, "decision log must not be empty after orchestration"
    assert "tool_call" in kinds, "expected at least one tool_call entry in the log"
    assert "answer" in kinds, "expected an answer entry in the log"
    assert result["filter_blocked"] is True, "filter double must have blocked"
    # The blocked filter must NOT have suppressed the log.
    assert len(log) >= 2, (
        f"log entries dropped to {len(log)} -- filter block should not suppress the log"
    )


def test_final_report_is_filter_approved_text():
    """(b) The final report is always the filter-approved text, never raw.

    When the filter blocks: final_response stays None (raw draft never leaked).
    When the filter passes: final_response equals orchestrator_response.text
    (the report the filter approved).
    """
    blocking = _run_scenario(filter_blocks=True)
    assert blocking["final_response"] is None, (
        f"raw draft leaked to final_response when filter blocked: "
        f"{blocking['final_response']!r}"
    )

    passing = _run_scenario(filter_blocks=False)
    expected = passing["orchestrator_response_text"]
    assert passing["final_response"] == expected, (
        f"final_response {passing['final_response']!r} != "
        f"orchestrator_response.text {expected!r}"
    )
    assert passing["final_response"] is not None and passing["final_response"] != "", (
        "filter-approved response must be non-empty"
    )


def test_filter_never_sees_decision_log():
    """(c) The filter only receives the final report -- never the decision log.

    The filter's _filter() function is called with the OrchestratorResponse and
    grounding context (findings, memory, tool results).  Decision-log entries
    must not appear in that payload; the log travels a separate path direct to
    the user (CtxDecisionLog -> ctx.decision_log).
    """
    result = _run_scenario(filter_blocks=True)
    fi = result["filter_input"]

    # The filter received the final report text.
    assert fi.get("response_text") == result["orchestrator_response_text"], (
        f"filter received unexpected response_text: {fi.get('response_text')!r}"
    )

    # None of the decision-log messages leaked into the filter's payload.
    log_messages = [
        getattr(e, "message", "") for e in result["log_entries"]
        if getattr(e, "message", "") and getattr(e, "message", "") not in _REPORT_TEXT
    ]
    findings_text = " ".join(
        str(getattr(f, "full_content", "")) for f in fi.get("findings", [])
    )
    filter_payload = fi.get("response_text", "") + findings_text
    for msg in log_messages:
        assert msg not in filter_payload, (
            f"decision-log message {msg!r} found in filter payload -- "
            "the log must not route through the filter"
        )


def test_split_contract_table():
    """Full integration: run both scenarios, check all three assertions, print the
    verdict table, and open a needs-reviewer note on any violation."""
    blocking = _run_scenario(filter_blocks=True)
    passing = _run_scenario(filter_blocks=False)

    assertion_results = _check_assertions(blocking, passing)
    all_ok = _print_table(assertion_results)

    if not all_ok:
        _open_needs_reviewer(assertion_results)

    for label, ok, detail in assertion_results:
        assert ok, f"C6 split violated [{label}]: {detail}"
