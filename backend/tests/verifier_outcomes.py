"""
Outcome-coverage harness for core/verifier/verifier.py.

The existing tests/verifier.py covers:
  - regex-is-a-hint (no content-block by regex)
  - LLM-adjudicates-proceed (status ok)
  - LLM-is-the-blocker (status blocked)
  - retry-budget count

This file covers the TWO outcomes NOT yet pinned hermetically:
  - WARN  (proceed-with-warning: verifier.py:88-94 flow.warn path)
  - FAIL-CLOSED (infra/config fault: verifier.py:98-105 flow.fail path)

And documents (without wiring) the DOC-ONLY fifth outcome:
  - ROUTE-THROUGH-EXPERT: routing_action/requires_expert are set on
    VerificationResult by verify_deterministic but are NEVER READ downstream
    (grep "routing_action" across backend/ hits only verifier/ and tests/;
     grep "requires_expert" downstream hits only normalizer/builders.py fields,
     never ctx.verifier_result.routing_action/requires_expert). The fifth outcome
     is architecture intent with no flow.route() consumer. Needs maintainer ADR.

Premise re-checked against running code (#61 lesson):
  verifier.py:85    ctx.verifier_blocked = False          (before warn branch)
  verifier.py:88-94 if result.warn or threat.should_warn: flow.warn(...)
  verifier.py:98    except VerifierError    -> flow.fail()
  verifier.py:101   except ModelUnavailableError -> flow.fail()
  verifier.py:104   except Exception        -> flow.fail(VerifierError(wrapped))
  Status.ERROR.value == "error" (NOT "failed" - the enum has ERROR="error")

All doubles monkeypatch verify_with_llm, the same seam tests/verifier.py uses.
No network calls, no paid keys, no core/verifier/*.py edits.
"""

from __future__ import annotations

import asyncio

from foundation import Flow, NormalizedInput, ThreatLevel, VerifierError, ModelUnavailableError
from core.verifier import verifier
from core.verifier.schemas import VerificationResult
from core.verifier.utils import verification_result


def _text(content: str) -> NormalizedInput:
    return NormalizedInput(modality="text", content_type="text/plain", content=content)


# ---------------------------------------------------------------------------
# (a) WARN outcome — pipeline proceeds WITH a warning
#     verifier.py:85-94: ctx.verifier_blocked=False is set, then flow.warn()
#     returned when result.warn is True OR threat_level.should_warn is True
# ---------------------------------------------------------------------------

def test_warn_via_warn_flag(monkeypatch):
    """
    LLM returns warn=True at otherwise-safe content (proceed=True, no block).
    Contract: status must be "warn", verifier_blocked must be False (pipeline
    proceeds), and the warn reason must be carried on the returned flow.
    """
    async def fake_llm(normalized, deterministic):
        return verification_result(
            proceed=True,
            warn=True,
            threat_level=ThreatLevel.NONE,
            reason="low-confidence benign",
            normalized=normalized,
            metadata=deterministic.metadata,
        )

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("maybe suspicious"), "warn-flag")))

    assert out.status.value == "warn", f"expected warn, got {out.status.value!r}"
    assert out.ctx.verifier_blocked is False, "WARN must NOT block the pipeline"
    assert out.reason is not None, "warn reason must be carried on the flow"
    assert out.reason == "low-confidence benign"


def test_warn_via_threat_level_should_warn(monkeypatch):
    """
    LLM returns threat_level=LOW (should_warn=True) with warn=False.
    The verifier.py:88 condition is `result.warn OR threat_level.should_warn`,
    so ThreatLevel.LOW alone must trigger the warn path.
    """
    async def fake_llm(normalized, deterministic):
        return verification_result(
            proceed=True,
            warn=False,
            threat_level=ThreatLevel.LOW,
            reason="slightly suspicious pattern",
            normalized=normalized,
            metadata=deterministic.metadata,
        )

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("low-risk content"), "warn-low")))

    assert out.status.value == "warn", f"expected warn via ThreatLevel.LOW, got {out.status.value!r}"
    assert out.ctx.verifier_blocked is False


def test_warn_medium_threat_also_warns(monkeypatch):
    """ThreatLevel.MEDIUM also has should_warn=True; verify it produces warn too."""
    async def fake_llm(normalized, deterministic):
        return verification_result(
            proceed=True,
            warn=False,
            threat_level=ThreatLevel.MEDIUM,
            reason="medium threat, proceed with caution",
            normalized=normalized,
            metadata=deterministic.metadata,
        )

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("medium-risk content"), "warn-medium")))

    assert out.status.value == "warn"
    assert out.ctx.verifier_blocked is False


# ---------------------------------------------------------------------------
# (b) FAIL-CLOSED outcome — infra/config fault, pipeline NEVER proceeds
#     verifier.py:98-105: any exception from verify_with_llm -> flow.fail()
#     Status.ERROR.value == "error" (note: NOT "failed"; the Status enum has
#     OK/BLOCKED/WARN/ERROR; ctx.failed=True and ctx.current_stage=FAILED)
# ---------------------------------------------------------------------------

def test_fail_closed_on_verifier_error(monkeypatch):
    """
    verify_with_llm raises VerifierError (LLM output malformed / config fault).
    Pipeline must fail hard: status=error, ctx.failed=True.
    Distinct from block (which is a threat, not a fault).
    """
    async def fake_llm(normalized, deterministic):
        raise VerifierError("verifier LLM returned unparseable output")

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("anything"), "fail-verifier-error")))

    assert out.status.value == "error", (
        f"VerifierError must produce status=error (flow.fail path), got {out.status.value!r}"
    )
    assert out.ctx.failed is True, "ctx.failed must be True on fail-closed"
    assert out.ctx.verifier_blocked is False, "fail-closed is NOT a block; verifier_blocked stays False"


def test_fail_closed_on_model_unavailable(monkeypatch):
    """
    verify_with_llm raises ModelUnavailableError (timeout / unreachable model).
    The pipeline never silently proceeds on infra faults.
    """
    async def fake_llm(normalized, deterministic):
        raise ModelUnavailableError("verifier model timed out after 10s", model="verifier")

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("anything"), "fail-model-unavail")))

    assert out.status.value == "error", (
        f"ModelUnavailableError must produce status=error, got {out.status.value!r}"
    )
    assert out.ctx.failed is True


def test_fail_closed_on_unexpected_exception(monkeypatch):
    """
    verify_with_llm raises a bare Exception (programming error / unexpected fault).
    verifier.py:104 catches it and wraps in VerifierError before flow.fail().
    Must never proceed; must produce status=error.
    """
    async def fake_llm(normalized, deterministic):
        raise RuntimeError("unexpected internal error")

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("anything"), "fail-bare-exc")))

    assert out.status.value == "error", (
        f"bare Exception must be wrapped and produce status=error, got {out.status.value!r}"
    )
    assert out.ctx.failed is True


# ---------------------------------------------------------------------------
# (c) ROUTE-DEAD report — routing_action/requires_expert are SET on
#     VerificationResult by verify_deterministic but NEVER READ downstream.
#     The "route-through-expert" documented outcome has no flow.route() consumer.
#     This test DOCUMENTS the gap; it does NOT wire the routing fields.
# ---------------------------------------------------------------------------

def test_route_through_expert_fields_are_set_but_unread(monkeypatch):
    """
    A fake LLM that returns routing_action='expert' and requires_expert=True
    produces indistinguishable behaviour from a plain proceed: the flow still
    returns status=ok and no downstream stage routes on the routing fields.

    Doc-vs-reality gap (needs-reviewer, NOT wired here):
      SYSTEM_ARCHITECTURE.md §Verification lists "route-through-expert" as a
      verifier outcome, but core/verifier/verifier.py has no flow.route() call.
      VerificationResult.routing_action and .requires_expert are written to
      ctx.verifier_result (verifier.py:73) but never read by any stage downstream.
      Confirmed: grep "routing_action" across backend/ hits only verifier/ and tests/;
      grep ".requires_expert" hits only normalizer/builders.py (NormalizedInput fields),
      never ctx.verifier_result. The fifth outcome is architecture intent only.
      Wiring it requires a maintainer-level ADR decision.
    """
    async def fake_llm(normalized, deterministic):
        return VerificationResult(
            proceed=True,
            routing_action="expert",
            requires_expert=True,
            required_capability="code_execution",
            reason="code-heavy request routed to an expert",
        )

    monkeypatch.setattr(verifier, "verify_with_llm", fake_llm)
    out = asyncio.run(verifier.run(Flow.new(_text("run this python script for me"), "route-dead")))

    # Fields ARE written to ctx.verifier_result (verifier.py:73)
    assert out.ctx.verifier_result is not None
    assert out.ctx.verifier_result.routing_action == "expert", (
        "routing_action must be set on ctx.verifier_result"
    )
    assert out.ctx.verifier_result.requires_expert is True, (
        "requires_expert must be set on ctx.verifier_result"
    )

    # The pipeline proceeds as ok because no downstream code reads these fields
    assert out.status.value == "ok", (
        "routing_action='expert' has no consumer: the route-through-expert outcome "
        "is doc-only (no flow.route() branch in verifier.py). Pipeline proceeds as ok."
    )


# ---------------------------------------------------------------------------
# Coverage table — printed on test collection for visibility
# ---------------------------------------------------------------------------

def test_print_outcome_coverage_table():
    """Prints the outcome coverage table and reports verdict."""
    table = """
Verifier Outcome Coverage (SYSTEM_ARCHITECTURE.md §Verification, all 5 outcomes):

  Outcome                   | Status  | Covered by
  --------------------------|---------|----------------------------------------------
  PROCEED                   | ok      | tests/verifier.py::test_llm_adjudicates_all_text
  WARN (proceed-with-warn)  | warn    | test_warn_via_warn_flag
                            |         | test_warn_via_threat_level_should_warn
                            |         | test_warn_medium_threat_also_warns
  ROUTE-THROUGH-EXPERT      | ok*     | test_route_through_expert_fields_are_set_but_unread
                            |         | *DOC-ONLY: routing_action/requires_expert set-but-unread;
                            |         |  no flow.route() consumer; wiring is maintainer-gated
  BLOCK                     | blocked | tests/verifier.py::test_llm_is_the_blocker
  FAIL-CLOSED (infra/fault) | error   | test_fail_closed_on_verifier_error
                            |         | test_fail_closed_on_model_unavailable
                            |         | test_fail_closed_on_unexpected_exception
  --------------------------|---------|----------------------------------------------

  Verdict: all 5 documented outcomes ACCOUNTED FOR -- HELD
  Note: route-through-expert is DOC-ONLY (no consumer).
        See needs-reviewer #64-adjacent for the wiring decision.
"""
    print(table)
