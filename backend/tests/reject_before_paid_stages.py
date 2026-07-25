"""
Cross-cutting integration harness: reject-before-paid-stages gauntlet.

Proves that bad-or-excess load is rejected BEFORE the expensive paid LLM stages
by driving the real core.pipeline.run() entry point with the paid-model seam
counter-wrapped. All pre-rejection production code runs normally; only external
dependencies (ClamAV/YARA, Qdrant/embeddings, text-worker NLP) are stubbed to
keep the suite hermetic.

The paid-model seam is core.llm.framework.run_agent (and core.llm.search.run_agent
for the grounded-search path). Both modules do `from .retry import run_agent` at
import time, creating their own bindings; the counter therefore patches those
call-site bindings, not core.llm.retry directly.

Five pre-paid rejection classes (seam_counter == 0 for each):
  1. Oversize input     -> BlockReason.INPUT_TOO_LARGE    (intake)
  2. Rate-limited       -> BlockReason.RATE_LIMITED        (intake)
  3. Empty/malformed    -> BlockReason.MALFORMED_INPUT     (intake)
  4. Malware pre-gate   -> BlockReason.MALICIOUS_CONTENT   (sanitizer, pre-LLM)
  5. Verifier det. block-> BlockReason.VERIFIER_REJECTED   (verifier, pre-LLM)

One verifier-LLM-block case (paid verifier adjudication only; orchestrator fan-out
and output filter provably skipped):
  6. Verifier LLM block -> BlockReason.VERIFIER_REJECTED   (verifier LLM monkeypatched)

Hermetic guarantees:
  - seam_counter RAISES if run_agent is ever called, making accidental LLM calls
    an explicit hard failure rather than a silent pass
  - pre_sanitization.run and text.scan stubbed; no ClamAV/YARA binary required
  - memory manager hydrate stubbed; no Qdrant or fastembed model required
  - all monkeypatches target the exact name used at the call-site (never the
    source module), matching the Python attribute-lookup semantics
"""

from __future__ import annotations

import asyncio

import pytest

from foundation import BlockReason, HydrationPackage, Origin, ThreatLevel
import settings
from core.intake import rate_limiter
from security.sanitizers import pre_sanitization
from security.sanitizers.pre_sanitization import PreSanitizationResult
from security.sanitizers.workers import text as text_worker
from security.sanitizers.workers.text import TextScanResult
from core import pipeline
import core.llm.framework as framework_mod
import core.llm.search as search_mod
import core.verifier.verifier as verifier_door


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Keep rate-limiter state clean between tests (mirrors tests/intake.py)."""
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()
    yield
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()


@pytest.fixture()
def seam_counter(monkeypatch):
    """
    Wrap the paid-model seam with a call counter that RAISES immediately if
    reached.  Any accidental LLM call becomes a hard test failure rather than a
    silent, cost-incurring pass.

    core.llm.framework and core.llm.search each do `from .retry import run_agent`
    at import time, binding run_agent into their own module namespaces.  Patching
    core.llm.retry would not rebind those copies.  The counter therefore patches
    the call-site names directly:
      - framework_mod.run_agent: every LLM stage (verifier, filter, orchestrator,
        experts) calls run_agent through framework.run_structured -> framework.run_agent
      - search_mod.run_agent: the grounded-search path inside the orchestrator's
        web_search tool calls search.run_agent
    Both patches are belt-and-suspenders; none of the six rejection cases reach
    either seam, but patching both makes the guard complete for future cases too.
    """
    counter = {"calls": 0}

    async def counted_sentinel(*args, **kwargs):
        counter["calls"] += 1
        raise AssertionError(
            f"run_agent reached (call #{counter['calls']}): "
            "a paid model call must not occur before a rejection gate fires"
        )

    monkeypatch.setattr(framework_mod, "run_agent", counted_sentinel)
    monkeypatch.setattr(search_mod, "run_agent", counted_sentinel)
    return counter


@pytest.fixture()
def _sanitizer_passes(monkeypatch):
    """
    Stub the sanitizer layer so it always passes cleanly (no external binaries).

    Patches:
      pre_sanitization.run  - replaces the ClamAV/YARA pre-gate with a clean stub
      text_worker.scan      - replaces the detect-secrets/Presidio worker
    Both patches target the name at the call-site in runner.py.
    """
    async def clean_pre(raw):
        return PreSanitizationResult()  # threat_level=NONE, passed=True by default

    async def clean_text(raw):
        return TextScanResult(threat_level=ThreatLevel.NONE)

    monkeypatch.setattr(pre_sanitization, "run", clean_pre)
    monkeypatch.setattr(text_worker, "scan", clean_text)


@pytest.fixture()
def _memory_no_op(monkeypatch):
    """
    Stub the MemoryManager singleton so hydration_prefetch returns immediately
    without attempting to connect to Qdrant or load fastembed models.

    The singleton is imported from core.memory (re-exported in __init__.py);
    patching its instance attribute overrides the class method for the duration
    of the test and is restored automatically by monkeypatch teardown.
    """
    from core.memory import manager as mem_singleton

    async def fake_hydrate(request):
        return HydrationPackage()

    monkeypatch.setattr(mem_singleton, "hydrate", fake_hydrate)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _run(payload, *, session_id="s", user_id="u"):
    """Run one pipeline turn synchronously and return the final Flow."""
    return asyncio.run(pipeline.run(payload, session_id, user_id))


# ---------------------------------------------------------------------------
# 1-3: Intake rejections
# The pipeline is blocked BEFORE the sanitizer fires.  No external dependency
# is touched; the seam is never reachable.
# ---------------------------------------------------------------------------

def test_oversize_blocked_before_paid_stages(seam_counter):
    """Input exceeding settings.INTAKE.max_input_size_bytes is blocked at intake; seam never reached."""
    big = "x" * (settings.INTAKE.max_input_size_bytes + 1)
    out = _run(big, session_id="s-oversize")

    assert out.status.value == "blocked"
    assert out.reason == BlockReason.INPUT_TOO_LARGE.value
    assert seam_counter["calls"] == 0


def test_rate_limited_blocked_before_paid_stages(seam_counter):
    """Exhausting the caller's rate-limit window blocks at intake; seam never reached."""
    # The limiter keys on the authenticated user_id (issue #18 — session ids are
    # rotatable), so pre-fill the window under the user this run carries ("u").
    # Direct calls to _identity_rate_limiter.allow() bypass the global window,
    # preventing accidental global-limiter pollution across tests.
    for _ in range(settings.INTAKE.rate_limit_max_requests):
        rate_limiter._identity_rate_limiter.allow("u")

    out = _run("hello", session_id="s-rate-limit")

    assert out.status.value == "blocked"
    assert out.reason == BlockReason.RATE_LIMITED.value
    assert seam_counter["calls"] == 0


def test_empty_input_blocked_before_paid_stages(seam_counter):
    """Empty string is blocked as MALFORMED_INPUT at intake; seam never reached."""
    out = _run("", session_id="s-empty")

    assert out.status.value == "blocked"
    assert out.reason == BlockReason.MALFORMED_INPUT.value
    assert seam_counter["calls"] == 0


# ---------------------------------------------------------------------------
# 4: Sanitizer rejection (malware pre-gate)
# The ClamAV/YARA pre-gate is replaced with a high-threat stub.  The runner
# blocks BEFORE scheduling any modality worker or touching the verifier or
# any LLM stage.
# ---------------------------------------------------------------------------

def test_malware_pregated_before_paid_stages(seam_counter, monkeypatch):
    """High-threat pre-sanitization result blocks at the sanitizer; seam never reached."""
    async def high_threat(raw):
        return PreSanitizationResult(
            threat_level=ThreatLevel.HIGH,
            reason="EICAR test signature matched",
            passed=False,
        )

    monkeypatch.setattr(pre_sanitization, "run", high_threat)

    out = _run("suspicious payload", session_id="s-malware")

    assert out.status.value == "blocked"
    assert out.reason == BlockReason.MALICIOUS_CONTENT.value
    assert seam_counter["calls"] == 0


# ---------------------------------------------------------------------------
# 5: Verifier deterministic rejection (pre-LLM path)
# verify_deterministic() returns a blocking result before verify_with_llm() is
# ever called, so run_agent is never reached and the seam counter stays at 0.
# ---------------------------------------------------------------------------

def test_verifier_deterministic_block_before_paid_stages(
    seam_counter, _sanitizer_passes, _memory_no_op, monkeypatch
):
    """
    Verifier deterministic block stops the flow before any LLM call; seam never reached.

    Patching verifier_door.verify_deterministic targets the name used at
    call-site inside verifier.run() (``result = verify_deterministic(flow, normalized)``),
    so the patch is effective regardless of where the function was defined.
    """
    from core.verifier.schemas import VerificationResult

    def blocking_deterministic(flow, normalized):
        return VerificationResult(
            proceed=False,
            dangerous=True,
            threat_level=ThreatLevel.HIGH,
            reason="deterministic gate: content classification blocked",
            categories=["verifier_rejected"],
        )

    monkeypatch.setattr(verifier_door, "verify_deterministic", blocking_deterministic)

    out = _run("some input text", session_id="s-det-block")

    assert out.status.value == "blocked"
    assert out.reason == BlockReason.VERIFIER_REJECTED.value
    assert seam_counter["calls"] == 0


# ---------------------------------------------------------------------------
# 6: Verifier LLM rejection
# The verifier LLM adjudicates and blocks the input (no real network call — it
# is monkeypatched).  The orchestrator multi-expert fan-out and the output
# filter are provably skipped: the seam counter stays 0 AND the flow journal
# carries no orchestrator or filter origin.
# ---------------------------------------------------------------------------

def test_verifier_llm_block_never_reaches_orchestrator(
    seam_counter, _sanitizer_passes, _memory_no_op, monkeypatch
):
    """
    Verifier LLM marks input dangerous; orchestrator fan-out and filter never execute.

    Three complementary assertions prove the invariant:
      (a) seam_counter == 0 — paid multi-expert fan-out seam never touched
      (b) journal origins contain no ORCHESTRATOR or FILTER — stages were skipped,
          not just silently failed
      (c) ctx.orchestrator_response is None — orchestrator produced no output

    Patching verifier_door.verify_with_llm targets the name used at call-site
    inside verifier.run(), so it intercepts the real LLM dispatch path hermetically
    without touching any locked verifier prompt file.
    """
    from core.verifier.utils import verification_result

    async def blocking_llm(normalized, deterministic):
        return verification_result(
            proceed=False,
            dangerous=True,
            threat_level=ThreatLevel.HIGH,
            reason="llm classified as malicious",
            categories=["malicious_code"],
            normalized=normalized,
        )

    monkeypatch.setattr(verifier_door, "verify_with_llm", blocking_llm)

    out = _run("do something harmful", session_id="s-llm-block")

    # (a) flow is blocked at the verifier
    assert out.status.value == "blocked"
    assert out.reason == BlockReason.VERIFIER_REJECTED.value
    # (a) the paid multi-expert seam was never reached
    assert seam_counter["calls"] == 0

    # (b) orchestrator and filter stages are provably absent from the journal
    journal_origins = {e.origin for e in out.journal if e.origin}
    assert Origin.ORCHESTRATOR not in journal_origins, (
        "orchestrator stage ran after verifier LLM block — "
        "expensive multi-expert fan-out was exposed to a rejected input"
    )
    assert Origin.FILTER not in journal_origins, (
        "output filter ran after verifier LLM block — "
        "filter executed without orchestrator output"
    )

    # (c) orchestrator produced no response (never ran)
    assert out.ctx.orchestrator_response is None
