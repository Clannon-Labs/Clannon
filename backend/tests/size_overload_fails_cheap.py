"""
Hermetic resilience test: oversized inputs fail at the cheap guard.

Two size caps from foundation/vocab/constants.py:

1. MAX_INPUT_SIZE_BYTES (50 MB, INTAKE)
   Any payload exceeding this cap is blocked at intake — the first and cheapest
   pipeline stage — before any sanitizer, verifier, normalizer, or orchestrator
   runs. Tripwires on verify_with_llm and run_loop prove zero model calls occur.

2. MAX_TEXT_INPUT_CHARS (100 k chars, NORMALIZER)
   A text payload that passes the byte cap but exceeds the char limit is truncated
   in the code-only normalizer before the verifier or orchestrator ever see it.
   No model call is needed to enforce this cap; the normalizer test confirms it.

Hermetic: no ClamAV, no Qdrant, zero API spend.
Serves: Critical Benchmarks 5 and 6 (security resilience + architectural robustness).
"""

import asyncio

import pytest

from foundation import Flow, BlockReason, Origin, constants
from core.intake import intake, rate_limiter
from core.normalizer import builders
import core.verifier.verifier as verifier_mod
import core.orchestrator.orchestrator as orch_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_intake(payload, *, session: str) -> Flow:
    """Run the intake stage synchronously and return the resulting Flow."""
    return asyncio.run(intake.process(Flow.new(payload, session)))


def _tripwire_model_calls(monkeypatch) -> None:
    """
    Replace the two LLM entry points with sentinels that fail the test if called.

    verify_with_llm and run_loop are the earliest points where a paid model call
    can occur. If either fires on an oversize input the guard did not fire in time.
    """
    async def _no_verify(*args, **kwargs):
        raise AssertionError(
            "TRIPWIRE: verify_with_llm was called — the oversized input must be "
            "rejected at intake before the verifier stage is reached."
        )

    async def _no_loop(*args, **kwargs):
        raise AssertionError(
            "TRIPWIRE: run_loop was called — the oversized input must be "
            "rejected at intake before the orchestrator stage is reached."
        )

    monkeypatch.setattr(verifier_mod, "verify_with_llm", _no_verify)
    monkeypatch.setattr(orch_mod, "run_loop", _no_loop)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Keep tests independent of the shared in-process limiter state."""
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()
    yield


# ---------------------------------------------------------------------------
# MAX_INPUT_SIZE_BYTES — rejected at intake, no model call
# ---------------------------------------------------------------------------

class TestMaxInputSizeBytes:
    """
    A payload exceeding MAX_INPUT_SIZE_BYTES (50 MB) must be blocked at the
    intake stage before any sanitizer, verifier, or orchestrator stage runs.
    """

    def test_binary_oversize_blocked_before_any_model_call(self, monkeypatch):
        """
        Binary payload one byte over the cap is rejected at intake.
        Tripwires on verify_with_llm and run_loop prove no model call occurs.
        """
        _tripwire_model_calls(monkeypatch)

        # One byte over. bytes is used so _input_size_bytes does len() only —
        # no second allocation for UTF-8 encoding as there would be for a str.
        payload = b"A" * (constants.MAX_INPUT_SIZE_BYTES + 1)

        out = _run_intake(payload, session="binary-oversize-tripwire")

        # If either tripwire fired it would have raised AssertionError above;
        # reaching these assertions proves the guard fired before any LLM stage.
        assert out.status.value == "blocked"
        assert out.reason == BlockReason.INPUT_TOO_LARGE.value
        assert out.meta.origin == Origin.INTAKE

    def test_text_str_encoding_also_blocked(self, monkeypatch):
        """
        A str payload whose UTF-8 byte length exceeds the cap is also blocked.
        Covers the encoding path: intake measures len(str.encode('utf-8')).
        """
        _tripwire_model_calls(monkeypatch)

        # ASCII: 1 char = 1 byte, so byte length == char count here.
        payload = "X" * (constants.MAX_INPUT_SIZE_BYTES + 1)

        out = _run_intake(payload, session="str-oversize-tripwire")

        assert out.status.value == "blocked"
        assert out.reason == BlockReason.INPUT_TOO_LARGE.value
        assert out.meta.origin == Origin.INTAKE

    def test_boundary_exactly_at_limit_passes_intake(self):
        """
        A text payload of exactly MAX_INPUT_SIZE_BYTES bytes must NOT be blocked.
        The intake check is strict (>), so exactly-at-limit is allowed through.
        Binary blobs of this size are not tested here: libmagic may reject unknown
        MIME types for uniform-byte buffers, which is expected modality-check
        behaviour, not a size-guard failure.
        """
        # ASCII str: 1 char = 1 UTF-8 byte.  _detect_modality returns TEXT without
        # libmagic, so modality detection cannot interfere with the size boundary.
        exactly = "B" * constants.MAX_INPUT_SIZE_BYTES

        out = _run_intake(exactly, session="exact-limit")

        assert out.status.value == "ok"


# ---------------------------------------------------------------------------
# MAX_TEXT_INPUT_CHARS — truncated cheaply at the normalizer, no model call
# ---------------------------------------------------------------------------

class TestMaxTextInputChars:
    """
    Text exceeding MAX_TEXT_INPUT_CHARS (100 k chars) is bounded in the
    code-only normalizer stage — no LLM call, zero model spend.
    """

    def test_oversize_text_truncated_at_normalizer(self):
        """
        normalize_payload truncates oversized text to exactly MAX_TEXT_INPUT_CHARS
        and marks the result as truncated. No model is involved.
        """
        oversized = "x" * (constants.MAX_TEXT_INPUT_CHARS + 1)

        ni = builders.normalize_payload(oversized, modality="text")

        assert len(ni.content) == constants.MAX_TEXT_INPUT_CHARS
        assert ni.metadata["truncated"] is True
        assert ni.metadata["chars"] == constants.MAX_TEXT_INPUT_CHARS

    def test_at_char_limit_not_truncated(self):
        """Text of exactly MAX_TEXT_INPUT_CHARS chars must NOT be marked truncated."""
        exactly = "y" * constants.MAX_TEXT_INPUT_CHARS

        ni = builders.normalize_payload(exactly, modality="text")

        assert len(ni.content) == constants.MAX_TEXT_INPUT_CHARS
        assert ni.metadata["truncated"] is False

    def test_char_oversize_passes_intake_byte_check(self):
        """
        A text of MAX_TEXT_INPUT_CHARS + 1 chars is 100 001 bytes for ASCII —
        far under the 50 MB byte cap — so it must NOT be blocked at intake.
        The char cap is the normalizer's concern, not intake's.
        """
        oversized = "z" * (constants.MAX_TEXT_INPUT_CHARS + 1)

        out = _run_intake(oversized, session="char-oversize-intake-check")

        # Intake measures raw byte size only; this input is ~97 KB, not 50 MB.
        assert out.status.value == "ok"
