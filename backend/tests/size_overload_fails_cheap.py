"""
Hermetic resilience test: oversized inputs fail at the cheap guard.

Two size caps, both in settings.SECURITY / settings.INTAKE (config/backend/*.yaml):

1. settings.INTAKE.max_input_size_bytes (50 MB, INTAKE)
   Any payload exceeding this cap is blocked at intake — the first and cheapest
   pipeline stage — before any sanitizer, verifier, normalizer, or orchestrator
   runs. The end-to-end chain test (test_oversize_rejected_before_any_paid_stage_
   end_to_end) proves this with live tripwires on verify_with_llm and run_loop.

2. settings.SECURITY.max_text_input_chars (100 k chars, NORMALIZER)
   A text payload that passes the byte cap but exceeds the char limit is truncated
   in the code-only normalizer before the verifier or orchestrator ever see it.
   No model call is needed to enforce this cap; the normalizer test confirms it.

Hermetic: no Qdrant, zero API spend.
Serves: Critical Benchmarks 5 and 6 (security resilience + architectural robustness).
"""

import asyncio

import pytest

from foundation import Flow, BlockReason, Origin
import settings
from core.intake import intake, rate_limiter
from core.normalizer import builders
from core import normalizer, verifier, orchestrator
from security.sanitizers import runner as sanitizer_runner
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
    """Keep tests independent of the shared in-process limiter state.

    Reaches into _requests on the module-level singletons intentionally: there is
    no public reset API and the limiters are shared across the process lifetime.
    """
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()
    yield


# ---------------------------------------------------------------------------
# settings.INTAKE.max_input_size_bytes — rejected at intake, no model call
# ---------------------------------------------------------------------------

class TestMaxInputSizeBytes:
    """
    A payload exceeding settings.INTAKE.max_input_size_bytes (50 MB) must be blocked at the
    intake stage before any sanitizer, verifier, or orchestrator stage runs.
    """

    def test_binary_oversize_blocked_at_intake(self):
        """
        Binary payload one byte over the cap is rejected at intake.

        Uses bytes so _input_size_bytes does len() only — no second allocation
        for UTF-8 encoding as there would be for a str.
        """
        payload = b"A" * (settings.INTAKE.max_input_size_bytes + 1)

        out = _run_intake(payload, session="binary-oversize")

        assert out.status.value == "blocked"
        assert out.reason == BlockReason.INPUT_TOO_LARGE.value
        assert out.meta.origin == Origin.INTAKE

    def test_text_str_encoding_also_blocked_at_intake(self):
        """
        A str payload whose UTF-8 byte length exceeds the cap is also blocked.
        Covers the encoding path: intake measures len(str.encode('utf-8')).
        """
        # ASCII: 1 char = 1 byte, so byte length == char count here.
        payload = "X" * (settings.INTAKE.max_input_size_bytes + 1)

        out = _run_intake(payload, session="str-oversize")

        assert out.status.value == "blocked"
        assert out.reason == BlockReason.INPUT_TOO_LARGE.value
        assert out.meta.origin == Origin.INTAKE

    def test_oversize_rejected_before_any_paid_stage_end_to_end(self, monkeypatch):
        """
        Drive the real stage chain with live tripwires to prove the size guard
        short-circuits all downstream paid stages.

        Tripwires on verify_with_llm and run_loop become real regression guards
        here: if intake ever stops blocking an oversized input, or Flow.then()'s
        Railway short-circuit breaks, one of these sentinels fires and the test
        fails. The sanitizer stage is included in the chain but is never actually
        called — Flow.then() checks should_stop BEFORE invoking the next stage
        (foundation/transport/flow.py:506-508), so ClamAV is never contacted and
        the test remains hermetic.
        """
        _tripwire_model_calls(monkeypatch)

        payload = b"A" * (settings.INTAKE.max_input_size_bytes + 1)

        out = asyncio.run(Flow.chain(
            Flow.new(payload, "e2e-oversize"),
            [
                intake.process,
                sanitizer_runner.run,
                normalizer.run,
                verifier.run,
                orchestrator.run,
            ],
        ))

        assert out.status.value == "blocked"
        assert out.reason == BlockReason.INPUT_TOO_LARGE.value
        assert out.meta.origin == Origin.INTAKE

    def test_boundary_exactly_at_limit_passes_intake(self):
        """
        A text payload of exactly settings.INTAKE.max_input_size_bytes bytes must NOT be blocked.
        The intake check is strict (>), so exactly-at-limit is allowed through.
        Binary blobs of this size are not tested here: libmagic may reject unknown
        MIME types for uniform-byte buffers, which is expected modality-check
        behaviour, not a size-guard failure.
        """
        # ASCII str: 1 char = 1 UTF-8 byte.  _detect_modality returns TEXT without
        # libmagic, so modality detection cannot interfere with the size boundary.
        exactly = "B" * settings.INTAKE.max_input_size_bytes

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
        oversized = "x" * (settings.SECURITY.max_text_input_chars + 1)

        ni = builders.normalize_payload(oversized, modality="text")

        assert len(ni.content) == settings.SECURITY.max_text_input_chars
        assert ni.metadata["truncated"] is True
        assert ni.metadata["chars"] == settings.SECURITY.max_text_input_chars

    def test_at_char_limit_not_truncated(self):
        """Text of exactly MAX_TEXT_INPUT_CHARS chars must NOT be marked truncated."""
        exactly = "y" * settings.SECURITY.max_text_input_chars

        ni = builders.normalize_payload(exactly, modality="text")

        assert len(ni.content) == settings.SECURITY.max_text_input_chars
        assert ni.metadata["truncated"] is False

    def test_char_oversize_passes_intake_byte_check(self):
        """
        A text of MAX_TEXT_INPUT_CHARS + 1 chars is 100 001 bytes for ASCII —
        far under the 50 MB byte cap — so it must NOT be blocked at intake.
        The char cap is the normalizer's concern, not intake's.
        """
        oversized = "z" * (settings.SECURITY.max_text_input_chars + 1)

        out = _run_intake(oversized, session="char-oversize-intake-check")

        # Intake measures raw byte size only; this input is ~97 KB, not 50 MB.
        assert out.status.value == "ok"
