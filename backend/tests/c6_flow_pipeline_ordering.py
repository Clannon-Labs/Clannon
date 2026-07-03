"""
Hermetic consistency harness — C6 Multi-Agent Architectural Consistency.

Pins the runtime contract of the Flow pipeline:
  (1) ordering  — every stage in ACTIVE_STAGES runs exactly once, in the
                  documented order (intake -> sanitizer -> normalizer ->
                  hydration_prefetch -> verifier -> orchestrator -> filter ->
                  delivery)
  (2) transport — every inter-stage handoff goes through Flow.next / .block /
                  .warn / .fail; the journal proves this because each of those
                  methods appends a JournalEntry
  (3) bypass    — no stage is silently skipped

Test doubles replace every LLM / Qdrant / ClamAV / YARA call.  The real
pipeline code (pipeline.py + every stage module) runs verbatim.

On a genuine ordering or transport divergence the tests REPORT the failure
via a per-stage PASS/FAIL table printed before the assertion — they never
edit a stage to paper over the gap.

DISTINCT FROM:
  backend/scripts/e2e_smoke.py        — real paid run, real network
  scripts/check_invariants (PR #32)   — static grep on imports, not yet on main

SERVES: Critical Benchmark 6 (architectural-boundaries-collapse failure mode).
"""

from __future__ import annotations

import asyncio

from foundation import Flow, HydrationPackage, Origin, OrchestratorResponse, ThreatLevel
from core.pipeline import ACTIVE_STAGES, run as pipeline_run
from core.verifier.utils import verification_result
import core.verifier.verifier as verifier_mod
import core.orchestrator.orchestrator as orch_mod
from core.memory import manager as _mem_singleton
import security.filter.filter as filter_mod
from security.sanitizers import pre_sanitization
from security.sanitizers.workers import text as text_worker
from security.sanitizers.pre_sanitization import PreSanitizationResult
from security.sanitizers.workers.text import TextScanResult
from security.filter.schemas import FilterResult


# ---------------------------------------------------------------------------
# Documented stage-order contract
# Each entry: (stage name in ACTIVE_STAGES, expected Origin in journal)
# ---------------------------------------------------------------------------

EXPECTED_STAGE_ORDER: list[tuple[str, Origin]] = [
    ("intake",             Origin.INTAKE),
    ("sanitizer",          Origin.SANITIZER),
    ("normalizer",         Origin.NORMALIZER),
    ("hydration_prefetch", Origin.MEMORY),
    ("verifier",           Origin.VERIFIER),
    ("orchestrator",       Origin.ORCHESTRATOR),
    ("filter",             Origin.FILTER),
    ("delivery",           Origin.OUTPUT),
]

# Short brief: len < 40 keeps _is_substantive_turn False so memory writes
# are skipped and the test does not depend on Qdrant being up.
_BENIGN_BRIEF = "Research async Python."
_FAKE_ANSWER  = "Async programming is good."


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

def _install_doubles(monkeypatch) -> None:
    """Replace every LLM/store/network call with deterministic test doubles.

    Nothing here changes which stage runs or in what order — the pipeline.py
    driver, ACTIVE_STAGES list, and every stage module run verbatim.
    """
    # pre-sanitization (ClamAV/YARA) gate
    async def _clean_prescan(raw):
        return PreSanitizationResult()

    monkeypatch.setattr(pre_sanitization, "run", _clean_prescan)

    # text modality sanitizer worker
    async def _clean_text(raw):
        return TextScanResult(threat_level=ThreatLevel.NONE)

    monkeypatch.setattr(text_worker, "scan", _clean_text)

    # memory hydration — prevents unawaited-future noise when Qdrant is absent
    async def _empty_hydrate(request):
        return HydrationPackage()

    monkeypatch.setattr(_mem_singleton, "hydrate", _empty_hydrate)

    # verifier LLM
    async def _safe_verify(normalized, deterministic):
        return verification_result(proceed=True, normalized=normalized)

    monkeypatch.setattr(verifier_mod, "verify_with_llm", _safe_verify)

    # orchestrator reasoning loop (does not touch memory or Capabilities)
    async def _fake_loop(normalized, ports, ctx):
        return OrchestratorResponse(text=_FAKE_ANSWER, confidence=0.9)

    monkeypatch.setattr(orch_mod, "run_loop", _fake_loop)

    # output filter LLM
    async def _safe_filter(response, findings, memory, tool_calls):
        return FilterResult(proceed=True)

    monkeypatch.setattr(filter_mod, "_filter", _safe_filter)

    # suppress the CLI-mode answer dump from the delivery stage
    monkeypatch.setenv("VRAKSHA_CLI_QUIET", "1")


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_pipeline(monkeypatch) -> tuple[Flow, list[str]]:
    """Install doubles and drive the full ACTIVE_STAGES pipeline.

    Returns (final_flow, stages_called) where stages_called is the ordered
    list of stage names the driver actually invoked via on_stage.
    """
    _install_doubles(monkeypatch)

    stages_called: list[str] = []

    def _on_stage(stage):
        stages_called.append(stage.name)

    final_flow = asyncio.run(
        pipeline_run(
            _BENIGN_BRIEF,
            session_id="c6-harness",
            user_id="test-user",
            on_stage=_on_stage,
        )
    )
    return final_flow, stages_called


# ---------------------------------------------------------------------------
# Per-stage result table
# ---------------------------------------------------------------------------

def _build_rows(stages_called: list[str], journal_origins: list[Origin]) -> list[dict]:
    """Build a per-stage result record for the PASS/FAIL table.

    Three sub-claims per stage:
      called    — the driver invoked the stage
      ordered   — it was invoked at the right index in the call sequence
      transport — the journal has an entry for this stage (proves .next/.block/
                  .warn/.fail was called; free-form bypass would appear as a
                  missing entry or a pipeline crash)
    """
    rows = []
    for i, (name, expected_origin) in enumerate(EXPECTED_STAGE_ORDER):
        called   = name in stages_called
        ordered  = called and (stages_called.index(name) == i)
        # journal_origins[i] is position i in the per-stage slice (after Flow.new)
        transport = (
            i < len(journal_origins) and journal_origins[i] == expected_origin
        )
        rows.append(
            {
                "stage":           name,
                "expected_origin": expected_origin.value,
                "called":          called,
                "ordered":         ordered,
                "transport":       transport,
                "pass":            called and ordered and transport,
            }
        )
    return rows


def _print_table(rows: list[dict], final_status: str) -> None:
    col_w = [22, 14, 9, 13, 13, 8]
    headers = ["Stage", "Origin", "Called", "Ordered", "Flow xport", "Result"]

    def fmt(cells: list) -> str:
        return "  ".join(str(c).ljust(col_w[j]) for j, c in enumerate(cells))

    print()
    print("=== C6 Flow-Pipeline Ordering Harness ===")
    print(f"    final pipeline status: {final_status}")
    print()
    print(fmt(headers))
    print(fmt(["-" * w for w in col_w]))
    for r in rows:
        cells = [
            r["stage"],
            r["expected_origin"],
            "YES"          if r["called"]    else "MISSING",
            "YES"          if r["ordered"]   else "OUT-OF-ORDER",
            "PASS"         if r["transport"] else "FAIL",
            "PASS"         if r["pass"]      else "FAIL",
        ]
        print(fmt(cells))
    print()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_pipeline_ordering_and_flow_transport(monkeypatch):
    """Every stage runs in documented order and records a Flow journal entry.

    Prints the per-stage PASS/FAIL table before asserting so the exact point
    of divergence is visible without re-running under a debugger.

    Failure condition pinned: 'architectural boundaries collapse' (C6).
    """
    final_flow, stages_called = _run_pipeline(monkeypatch)

    # journal[0] = initial Flow.new entry; journal[1:] = one entry per stage
    journal_origins = [e.origin for e in final_flow.journal[1:]]

    rows = _build_rows(stages_called, journal_origins)
    _print_table(rows, final_flow.status.value)

    failures = [r for r in rows if not r["pass"]]
    assert not failures, (
        f"{len(failures)} stage(s) failed the ordering/transport contract: "
        + ", ".join(r["stage"] for r in failures)
    )


def test_pipeline_completes_and_delivers(monkeypatch):
    """Pipeline reaches status=ok and sets the expected final_response.

    Guards against a premature block or fail that would let the ordering
    test pass vacuously (all observed stages are correct, but the tail was
    never reached).
    """
    final_flow, _ = _run_pipeline(monkeypatch)

    assert final_flow.status.value == "ok", (
        f"Pipeline did not complete cleanly.  "
        f"status={final_flow.status.value!r}  "
        f"reason={final_flow.reason!r}  "
        f"error={final_flow.error!r}"
    )
    assert final_flow.ctx.final_response == _FAKE_ANSWER, (
        f"Delivery stage did not set the expected final_response.  "
        f"Got: {final_flow.ctx.final_response!r}"
    )


def test_no_stage_bypassed(monkeypatch):
    """Every stage listed in ACTIVE_STAGES is actually invoked.

    Catches premature should_stop that would silently skip the tail of the
    pipeline, leaving the ordering test with an incomplete picture.
    """
    final_flow, stages_called = _run_pipeline(monkeypatch)
    expected_names = [s.name for s in ACTIVE_STAGES]

    missing = [n for n in expected_names if n not in stages_called]
    extra   = [n for n in stages_called  if n not in expected_names]

    if missing or extra:
        print(f"\nMissing stages:    {missing}")
        print(f"Unexpected stages: {extra}")
        print(f"Called  : {stages_called}")
        print(f"Expected: {expected_names}")

    assert not missing, f"Stages in ACTIVE_STAGES not invoked: {missing}"
    assert not extra,   f"Stages invoked but absent from ACTIVE_STAGES: {extra}"


def test_every_handoff_goes_through_flow(monkeypatch):
    """One journal entry per stage — proves every stage called .next/.block/.warn/.fail.

    A stage that returns a non-Flow, or exits without a transition, would
    either crash the driver or appear as a missing journal entry here.
    This is the runtime 'no free-form text between stages' contract.
    """
    final_flow, stages_called = _run_pipeline(monkeypatch)

    # Subtract 1 for the initial Flow.new entry that precedes any stage
    n_journal_stage_entries = len(final_flow.journal) - 1
    n_stages_invoked        = len(stages_called)

    assert n_journal_stage_entries == n_stages_invoked, (
        f"Journal stage entries ({n_journal_stage_entries}) != "
        f"stages invoked ({n_stages_invoked}).  "
        f"A stage may have bypassed Flow transport, or produced more than one "
        f"transition.  Journal origins: "
        f"{[e.origin for e in final_flow.journal[1:]]}"
    )
