"""
tests/decision_log_filter_independence.py

Hermetic harness pinning the C6 architectural split:

    "the orchestrator's structured decision log streams DIRECTLY to the user
    while ONLY the final report buffers through the output filter"

Three contract assertions:
  (a) DECISION-LOG-DELIVERED  -- log entries survive a blocking filter verdict;
                                 the filter verdict cannot retroactively suppress
                                 them, even after the skipped delivery stage.
  (b) REPORT-FILTERED         -- final_response is always filter-approved text,
                                 never the raw orchestrator draft; when the filter
                                 blocks, final_response stays None AND the delivery
                                 stage never renders an answer to the user.
  (c) FILTER-SAW-LOG          -- the filter receives the final report only, never
                                 the decision-log entries.

Hermetic: no network, no paid keys.  The real orchestrator stage (orchestrator.py),
output filter stage (security/filter/filter.py), and delivery stage
(delivery/delivery.py) run under the REAL pipeline driver (core/pipeline.drive).
The LLM capability door, memory store, and the filter LLM call itself are test
doubles.

The real pipeline driver (core.pipeline.drive) is what decides whether delivery
runs -- NOT test-level logic.  When the filter blocks, the pipeline driver sees
flow.should_stop and breaks the stage loop before delivery is reached.  This pins
the production short-circuit, not a hand-rolled imitation of it.

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
import contextlib
import io
import os
import pathlib
from unittest.mock import patch

from foundation import (
    Flow,
    HydrationPackage,
    NormalizedInput,
)
from core import pipeline
from core.orchestrator import run as orchestrator_stage_run
from core.orchestrator.ports import Ports
from core.orchestrator.schemas import OrchestratorAnswer
from core.orchestrator.utils.decision_log import CtxDecisionLog
from registry.capabilities import ExpertFindings
import security.filter.filter as filter_mod
from security.filter import run as filter_stage_run
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

    Emits one tool-call event (search.web), buffers one expert finding, and
    returns an explicit report answer that references the finding. No model,
    no network.
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
            presentation="report",
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
    Drive a benign brief through the real orchestrator stage, real filter stage,
    and real delivery stage using the REAL pipeline driver (pipeline.drive()).

    FIX 1: pipeline.drive() is the driver.  The real short-circuit (flow.should_stop
    in the driver's stage loop) decides whether delivery runs -- NOT test logic.  A
    future regression that allowed delivery to run after a block would be caught here
    because the test never manually skips delivery; the driver does it, or doesn't.

    FIX 2: VRAKSHA_CLI_QUIET is not set so delivery renders normally.  stdout is
    captured via contextlib.redirect_stdout, allowing the tests to assert the
    user-visible ordering: decision-log entries first, filtered answer second.

    FIX 3: ctx.decision_log is read AFTER pipeline.drive() returns, proving that the
    entries survive the blocking filter verdict AND the skipped delivery stage.

    Returns a dict with state to assert against:
        log_entries     list[DecisionLogEntry]   -- ctx after the full pipeline run
        filter_called   bool                     -- did the filter run at all?
        filter_input    dict                     -- what the filter received
        final_response  str | None               -- what ended up as final output
        filter_blocked  bool
        orchestrator_response_text  str          -- raw draft before filter verdict
        cli_output      str                      -- captured stdout from delivery
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

    def _fake_build_ports(ctx):
        """Injected at the real seam (core.orchestrator.orchestrator.build_default_ports).
        Called by the REAL orchestrator.run stage door with the live ctx -- the same
        door that production uses.  Returns fake ports so no model/store is touched."""
        return Ports(
            caps=_FakeCaps(ctx),
            log=CtxDecisionLog(ctx),
        )

    async def _inner():
        # Seed the flow with a NormalizedInput so orchestrator.run can coerce it
        # as normal.  The upstream intake/sanitizer/normalizer/verifier stages are
        # intentionally omitted -- this harness pins only the orchestrator->filter->
        # delivery split.
        normalized = NormalizedInput(
            modality="text",
            content_type="text/plain",
            content=_BRIEF,
        )
        flow = Flow.new(normalized, session_id="s-harness", user_id="u-harness")

        # Three REAL stage functions in the production order.  pipeline.drive()
        # runs them Railway-style: flow.should_stop short-circuits the loop so
        # the real driver (not test code) decides whether delivery runs.
        stages = [
            pipeline.Stage(orchestrator_stage_run, "orchestrator", "working",    "orchestrating"),
            pipeline.Stage(filter_stage_run,       "filter",       "checking",   "filtering"),
            pipeline.Stage(delivery_run,           "delivery",     "delivering", "filtering"),
        ]

        # Ensure delivery render is not suppressed so the CLI output is exercised
        # and captured.  This is what the task cites (delivery.py:19-24).
        os.environ.pop("VRAKSHA_CLI_QUIET", None)

        stdout_buf = io.StringIO()
        with (
            # FIX 1: inject fakes at the real seam (orchestrator.run calls
            # build_default_ports(ctx) -- we replace it so the caps and memory
            # doors are our doubles while the stage door itself is untouched).
            patch("core.orchestrator.orchestrator.build_default_ports", _fake_build_ports),
            # The filter spy replaces only the LLM call (_filter) inside the real
            # filter.run -- the stage routing, block/pass logic, and ctx updates
            # all stay real.
            patch.object(filter_mod, "_filter", spy),
            # FIX 2: capture stdout so we can assert the user-visible ordering.
            contextlib.redirect_stdout(stdout_buf),
        ):
            flow = await pipeline.drive(flow, stages)

        ctx = flow.ctx
        # FIX 3: read ctx.decision_log AFTER the full pipeline (including the
        # blocking filter AND the skipped delivery stage) -- proving entries survive.
        return {
            "log_entries": list(ctx.decision_log),
            "filter_called": bool(filter_calls),
            "filter_input": filter_calls[0] if filter_calls else {},
            "final_response": ctx.final_response,
            "filter_blocked": ctx.filter_blocked,
            "orchestrator_response_text": (
                ctx.orchestrator_response.text if ctx.orchestrator_response else ""
            ),
            "cli_output": stdout_buf.getvalue(),
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
    # Decision-log entries must be present AFTER the full pipeline run (post-
    # pipeline snapshot), surviving the blocking filter verdict and the skipped
    # delivery stage.  The filter verdict must not retroactively suppress them.
    log = blocking_result["log_entries"]
    log_present = len(log) > 0
    log_has_tool_call = any(getattr(e, "kind", "") == "tool_call" for e in log)
    log_has_answer = any(getattr(e, "kind", "") == "answer" for e in log)
    a_ok = log_present and log_has_tool_call and log_has_answer
    results.append((
        "DECISION-LOG-DELIVERED",
        a_ok,
        (
            f"{len(log)} log entries present post-pipeline "
            f"(tool_call={log_has_tool_call}, answer={log_has_answer}) "
            "after filter block + skipped delivery"
        ),
    ))

    # --- (b) REPORT-FILTERED ------------------------------------------------
    # (b1) Blocking path: final_response must be None AND the delivery stage must
    #      not have rendered an answer to the user.  The real pipeline driver
    #      (pipeline.drive's should_stop check) is what keeps delivery from running
    #      -- the test never manually skips it, so a regression that called delivery
    #      anyway would surface as a non-empty cli_output or a non-None final_response.
    b1_no_response = blocking_result["final_response"] is None
    b1_no_render = "--- answer ---" not in blocking_result["cli_output"]
    b1_ok = b1_no_response and b1_no_render
    results.append((
        "REPORT-FILTERED (block)",
        b1_ok,
        (
            "final_response=None and no CLI answer section rendered when filter blocks"
            if b1_ok
            else (
                f"VIOLATION: final_response={blocking_result['final_response']!r}, "
                f"cli_output contains answer section: "
                f"{'--- answer ---' in blocking_result['cli_output']}"
            )
        ),
    ))

    # (b2) Passing path: final_response must equal the orchestrator_response.text
    #      the filter approved, AND the CLI output must render the decision-log
    #      section BEFORE the answer section (the user-visible ordering contract
    #      delivery.py:19-24 specifies).
    expected = passing_result["orchestrator_response_text"]
    b2_response_ok = passing_result["final_response"] == expected
    cli = passing_result["cli_output"]
    log_hdr = "--- decision log ---"
    ans_hdr = "--- answer ---"
    b2_order_ok = (
        log_hdr in cli
        and ans_hdr in cli
        and cli.index(log_hdr) < cli.index(ans_hdr)
    )
    b2_ok = b2_response_ok and b2_order_ok
    results.append((
        "REPORT-FILTERED (pass)",
        b2_ok,
        (
            f"final_response == orchestrator_response.text; "
            f"CLI renders log section before answer section"
            if b2_ok
            else (
                f"final_response={passing_result['final_response']!r} "
                f"(expected {expected!r}); "
                f"log_before_answer={b2_order_ok}"
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
        # verbatim in the filter payload -- which in our synthetic scenario they
        # do not, since the report text is distinct.
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
        "   delivery.py must only run after the filter passes.  Check pipeline.drive",
        "   -- the real driver's should_stop short-circuit is what enforces this.",
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
    """(a) Decision-log entries survive the full blocking pipeline run.

    Entries are populated during orchestration, before the filter runs.  The
    post-pipeline snapshot proves they survive both the blocking filter verdict
    and the delivery stage that was short-circuited by the real pipeline driver.
    """
    result = _run_scenario(filter_blocks=True)
    log = result["log_entries"]  # post-pipeline snapshot (FIX 3)
    kinds = [getattr(e, "kind", "") for e in log]
    assert len(log) > 0, "decision log must not be empty after pipeline run"
    assert "tool_call" in kinds, "expected at least one tool_call entry in the log"
    assert "answer" in kinds, "expected an answer entry in the log"
    assert result["filter_blocked"] is True, "filter double must have blocked"
    # The blocked filter must NOT have suppressed the log.
    assert len(log) >= 2, (
        f"log entries dropped to {len(log)} after blocking filter + skipped delivery -- "
        "filter block must not suppress the decision log"
    )


def test_final_report_is_filter_approved_text():
    """(b) The final report is always the filter-approved text, never raw.

    Blocking path: final_response stays None AND delivery renders nothing to the
    user -- proved by the real pipeline driver's should_stop short-circuit, NOT
    by the test skipping delivery manually.

    Passing path: final_response equals orchestrator_response.text (the report the
    filter approved), AND the CLI output shows the decision-log section BEFORE the
    answer section (delivery.py:19-24 user-visible ordering contract).
    """
    blocking = _run_scenario(filter_blocks=True)
    assert blocking["final_response"] is None, (
        f"raw draft leaked to final_response when filter blocked: "
        f"{blocking['final_response']!r}"
    )
    # Delivery must not have rendered an answer section when the filter blocked.
    # If "--- answer ---" appears in cli_output it means delivery ran despite the
    # block -- a regression in pipeline.drive's should_stop short-circuit.
    assert "--- answer ---" not in blocking["cli_output"], (
        "delivery rendered an answer section even though the filter blocked -- "
        "the real pipeline driver should have short-circuited before delivery"
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
    # Decision-log section must appear before the answer section in the CLI output.
    cli = passing["cli_output"]
    assert "--- decision log ---" in cli, "expected decision log section in CLI output"
    assert "--- answer ---" in cli, "expected answer section in CLI output"
    assert cli.index("--- decision log ---") < cli.index("--- answer ---"), (
        "decision log must be rendered before the answer in the user-visible output"
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
