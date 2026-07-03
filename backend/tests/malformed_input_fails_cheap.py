"""
Hermetic resilience test: malformed and unsupported inputs fail at the cheap guard.

Three structural categories of bad brief input are assessed against the cheap
pre-LLM chain (intake -> normalizer, sanitizer excluded for hermeticity):

1. MALFORMED BINARY — bytes payload with no recognisable media format.
   libmagic returns an unsupported MIME type; blocked at intake with
   UNSUPPORTED_MODALITY before any sanitizer, normalizer, or LLM stage runs.

2. UNSUPPORTED MIME (ZIP) — a real ZIP archive (local file header, PK signature).
   libmagic correctly identifies application/zip, which is not in the supported
   modality set. Blocked at intake with UNSUPPORTED_MODALITY.

3. EMPTY / WHITESPACE BRIEF — two sub-cases:
   a. Empty string (""): byte size == 0; blocked at intake with MALFORMED_INPUT.
   b. Whitespace only ("   "): byte size == 3, str -> TEXT modality detected
      without content sniffing (all str payloads are TEXT in intake). The flow
      passes intake AND the code-only normalizer, producing a NormalizedInput
      with content="   ". It is NOT blocked before the verifier (the first paid
      LLM stage). This is a REAL ROBUSTNESS GAP, documented here without faking
      a pass; see test_whitespace_would_reach_paid_stage and the summary table.

The cheap chain tested here skips the sanitizer stage (ClamAV / YARA), making the
suite fully hermetic — no ClamAV, no Qdrant, zero API spend.

Spy doubles on verify_with_llm and run_loop prove zero paid model calls occur for
all cases where a cheap guard fires. Each test function targets one assertion; the
final test_resilience_summary_table runs all four cases and prints a full table.

All findings were pinned by running the real code path FIRST with the cheap chain
before writing assertions (see the verification notes in each class docstring).

Serves: Critical Benchmark 5 (security resilience). Cycle-6 resilience suite.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from foundation import Flow, BlockReason, Origin
from core.intake import intake, rate_limiter
from core.normalizer import normalizer as norm_mod
from core.pipeline import Stage, drive
import core.verifier.verifier as verifier_mod
import core.orchestrator.orchestrator as orch_mod


# ---------------------------------------------------------------------------
# Test case definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Case:
    name: str
    payload: Any
    session: str
    expected_outcome: str   # "REJECTED-CHEAP" or "REACHED-PAID-STAGE"
    expected_reason: str | None = None  # BlockReason.value when rejected


CASES: list[_Case] = [
    _Case(
        name="malformed_binary_bytes",
        payload=b"\x00\x01\x02\x03\x04\x05\x06\x07" * 16,
        session="malformed-binary",
        expected_outcome="REJECTED-CHEAP",
        expected_reason=BlockReason.UNSUPPORTED_MODALITY.value,
    ),
    _Case(
        name="unsupported_zip_mime",
        payload=b"PK\x03\x04" + b"\x00" * 60,
        session="zip-mime",
        expected_outcome="REJECTED-CHEAP",
        expected_reason=BlockReason.UNSUPPORTED_MODALITY.value,
    ),
    _Case(
        name="empty_brief",
        payload="",
        session="empty-brief",
        expected_outcome="REJECTED-CHEAP",
        expected_reason=BlockReason.MALFORMED_INPUT.value,
    ),
    _Case(
        name="whitespace_only_brief",
        payload="   ",
        session="whitespace-brief",
        expected_outcome="REACHED-PAID-STAGE",
        expected_reason=None,
    ),
]


# ---------------------------------------------------------------------------
# Cheap chain: intake -> normalizer (sanitizer excluded — hermetic)
# ---------------------------------------------------------------------------

_CHEAP_CHAIN = [
    Stage(intake.process, "intake",     "taking it in", "sanitizing"),
    Stage(norm_mod.run,   "normalizer", "normalizing",  "verifying"),
]


def _run(payload: Any, session: str) -> Flow:
    """Run payload through the cheap chain synchronously."""
    flow = Flow.new(payload, session)
    return asyncio.run(drive(flow, _CHEAP_CHAIN))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Keep each test independent of shared in-process limiter state."""
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()
    yield
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()


@pytest.fixture(autouse=True)
def _spy_llm(monkeypatch):
    """
    Replace the two paid LLM entry points with spy doubles.

    verify_with_llm and run_loop are the earliest points where a paid model
    call can occur. None of the cheap-chain stages trigger them; the spies
    are a safety net that catches any unexpected call path. After each test
    the fixture asserts both spies recorded zero calls.
    """
    calls: list[str] = []

    async def _spy_verify(*_args, **_kwargs):
        calls.append("verifier.verify_with_llm")

    async def _spy_loop(*_args, **_kwargs):
        calls.append("orchestrator.run_loop")

    monkeypatch.setattr(verifier_mod, "verify_with_llm", _spy_verify)
    monkeypatch.setattr(orch_mod,     "run_loop",         _spy_loop)

    yield calls

    assert calls == [], (
        f"LLM spy detected unexpected paid call(s) during this test: {calls}"
    )


# ---------------------------------------------------------------------------
# Category 1: malformed binary bytes
# ---------------------------------------------------------------------------

class TestMalformedBinaryBytes:
    """
    A bytes payload whose content cannot be interpreted as a supported media
    format is blocked at intake with UNSUPPORTED_MODALITY.

    Reality pinned: b"\\x00..\\x07" * 16 -> libmagic -> unsupported MIME ->
    UNSUPPORTED_MODALITY block at intake. Normalizer never runs.
    """

    def test_blocked_at_intake_with_structured_reason(self):
        out = _run(b"\x00\x01\x02\x03\x04\x05\x06\x07" * 16, "malformed-bin-reason")
        assert out.blocked
        assert out.reason == BlockReason.UNSUPPORTED_MODALITY.value
        assert out.meta.origin == Origin.INTAKE

    def test_railway_short_circuit_stops_pipeline(self):
        out = _run(b"\x00\x01\x02\x03\x04\x05\x06\x07" * 16, "malformed-bin-sc")
        assert out.should_stop
        assert out.ctx.normalized_input is None, (
            "normalizer must not have run — normalized_input should be None"
        )


# ---------------------------------------------------------------------------
# Category 2: unsupported / mismatched MIME type (ZIP)
# ---------------------------------------------------------------------------

class TestUnsupportedZipMime:
    """
    A ZIP archive (PK local file header) is recognised by libmagic as
    application/zip, which is absent from the supported modality set.
    Blocked at intake with UNSUPPORTED_MODALITY.

    Reality pinned: b"PK\\x03\\x04" + 60 null bytes -> application/zip ->
    UNSUPPORTED_MODALITY block at intake. Normalizer never runs.
    """

    def test_zip_header_blocked_with_structured_reason(self):
        out = _run(b"PK\x03\x04" + b"\x00" * 60, "zip-reason")
        assert out.blocked
        assert out.reason == BlockReason.UNSUPPORTED_MODALITY.value
        assert out.meta.origin == Origin.INTAKE

    def test_normalizer_never_runs_for_unsupported_mime(self):
        out = _run(b"PK\x03\x04" + b"\x00" * 60, "zip-no-norm")
        assert out.ctx.normalized_input is None


# ---------------------------------------------------------------------------
# Category 3a: empty brief
# ---------------------------------------------------------------------------

class TestEmptyBrief:
    """
    An empty string has byte size == 0. Intake checks size first (before
    modality detection) and blocks with MALFORMED_INPUT.

    Reality pinned: "" -> size=0 -> MALFORMED_INPUT at intake.
    """

    def test_empty_string_blocked_with_structured_reason(self):
        out = _run("", "empty-reason")
        assert out.blocked
        assert out.reason == BlockReason.MALFORMED_INPUT.value
        assert out.meta.origin == Origin.INTAKE

    def test_empty_input_never_reaches_normalizer(self):
        out = _run("", "empty-no-norm")
        assert out.ctx.normalized_input is None


# ---------------------------------------------------------------------------
# Category 3b: whitespace-only brief (REAL ROBUSTNESS GAP)
# ---------------------------------------------------------------------------

class TestWhitespaceOnlyBrief:
    """
    Whitespace-only text ("   ") passes every cheap guard:
    - Intake: byte size == 3 > 0 (not blocked); str payload -> TEXT modality
      detected without content sniffing (no libmagic call for str).
    - Normalizer: _normalize_text produces NormalizedInput(content="   ").

    The flow exits the cheap chain in an OK, non-blocked state. The next
    pipeline stage is the verifier (paid LLM). This is a REAL ROBUSTNESS GAP.

    Reality pinned: "   " -> intake OK, normalizer OK,
    NormalizedInput.content="   " (3 spaces, not truncated).

    These tests PASS when the gap EXISTS. If a cheap whitespace guard is added
    later, the assertions must be updated to REJECTED-CHEAP.
    """

    def test_whitespace_passes_intake(self):
        """Whitespace text is not blocked by any cheap guard at intake."""
        out = asyncio.run(
            drive(Flow.new("   ", "ws-intake"), [_CHEAP_CHAIN[0]])
        )
        assert not out.blocked, (
            "whitespace no longer rejected at intake — gap is closed; "
            "update expected_outcome in CASES to REJECTED-CHEAP"
        )

    def test_whitespace_produces_normalized_input_with_whitespace_content(self):
        """
        After passing intake, the normalizer produces a NI whose content is
        pure whitespace. The pipeline is not blocked; the flow is forwarded.
        """
        out = _run("   ", "ws-ni-check")
        assert not out.should_stop
        ni = out.ctx.normalized_input
        assert ni is not None
        assert ni.content.strip() == "", (
            f"expected whitespace-only content, got {ni.content!r}"
        )

    def test_whitespace_would_reach_paid_stage(self):
        """
        DOCUMENTED GAP — this test asserts the gap IS present (flow is not
        blocked before the verifier). The cheap chain produces a non-blocked
        flow for whitespace input; the next stage would be verify_with_llm
        (a paid model call). No LLM spy fires here because the verifier stage
        is not in the cheap chain; see the summary table for the REACHED-PAID-STAGE
        flag.
        """
        out = _run("   ", "ws-gap-doc")
        assert not out.should_stop, (
            "UNEXPECTED: whitespace is now blocked before the paid stage — "
            "the gap documented here has been closed; update this test."
        )


# ---------------------------------------------------------------------------
# Summary table (run all cases; print REJECTED-CHEAP / REACHED-PAID-STAGE)
# ---------------------------------------------------------------------------

def test_resilience_summary_table():
    """
    Run all four cases through the cheap chain and print a per-case outcome
    table. Cases that reach the paid stage are flagged as REAL ROBUSTNESS GAPS.
    Expected-REJECTED cases are asserted to still be blocked (regression guard).

    Output is visible with `pytest -s` or in CI stdout capture.
    """
    rows: list[tuple[str, str, str]] = []
    real_gaps: list[str] = []

    for case in CASES:
        rate_limiter._identity_rate_limiter._requests.clear()
        rate_limiter._global_rate_limiter._requests.clear()

        out = _run(case.payload, f"table-{case.session}")

        if out.blocked:
            outcome = "REJECTED-CHEAP"
            detail  = out.reason or "blocked"
        elif out.ctx.failed:
            outcome = "REJECTED-CHEAP"
            detail  = "pipeline error (failed)"
        else:
            outcome = "REACHED-PAID-STAGE"
            detail  = f"next stage: verifier (paid LLM) — no cheap guard"
            real_gaps.append(case.name)

        rows.append((case.name, outcome, detail))

    # ---- print table --------------------------------------------------------
    col1 = max(len(r[0]) for r in rows)
    col2 = len("REACHED-PAID-STAGE")
    col3 = max(len(r[2]) for r in rows)
    sep  = f"+{'-'*(col1+2)}+{'-'*(col2+2)}+{'-'*(col3+2)}+"
    hdr  = f"| {'CASE'.ljust(col1)} | {'OUTCOME'.ljust(col2)} | {'DETAIL'.ljust(col3)} |"

    print("\n\n=== MALFORMED INPUT RESILIENCE REPORT ===")
    print(sep)
    print(hdr)
    print(sep)
    for name, outcome, detail in rows:
        print(f"| {name.ljust(col1)} | {outcome.ljust(col2)} | {detail.ljust(col3)} |")
    print(sep)

    if real_gaps:
        print("\n*** REAL ROBUSTNESS GAPS (input reached paid stage) ***")
        for g in real_gaps:
            case = next(c for c in CASES if c.name == g)
            payload_repr = (
                repr(case.payload)[:40] + "..."
                if len(repr(case.payload)) > 40
                else repr(case.payload)
            )
            print(f"  GAP: {g}")
            print(f"       payload type: {type(case.payload).__name__!r}")
            print(f"       payload:      {payload_repr}")
            print(f"       no cheap guard blocks this before the verifier LLM")
        print()

    # ---- assert expected-REJECTED cases remain blocked ----------------------
    for case in CASES:
        _, outcome, _ = next(r for r in rows if r[0] == case.name)
        if case.expected_outcome == "REJECTED-CHEAP":
            assert outcome == "REJECTED-CHEAP", (
                f"REGRESSION: {case.name} was expected REJECTED-CHEAP but now reaches "
                f"the paid stage. A cheap guard may have been removed or broken."
            )

    # ---- assert documented gaps match reality -------------------------------
    for case in CASES:
        _, outcome, _ = next(r for r in rows if r[0] == case.name)
        if case.expected_outcome == "REACHED-PAID-STAGE":
            assert outcome == "REACHED-PAID-STAGE", (
                f"GAP CLOSED: {case.name} now reports REJECTED-CHEAP. "
                f"Update expected_outcome in CASES and the class docstring above."
            )
