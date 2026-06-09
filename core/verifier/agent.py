"""Structured verifier agent (built on the core/llm framework adapter)."""

from __future__ import annotations

from functools import lru_cache

from foundation import (
    NormalizedInput,
    ThreatLevel,
    constants,
)
from registry.config import Prompt, get_prompt
from core.llm import build_agent, run_structured

from .schemas import VerificationResult, VerifierInputView, VerifierLLMResult
from .utils import content_excerpt, verification_result


@lru_cache(maxsize=1)
def _verifier_prompt() -> Prompt:
    """
    Resolve the verifier system prompt (with its version) from the prompt
    registry once and reuse it. The version is recorded on every result so a
    verdict can be traced back to the exact prompt that produced it.
    """
    return get_prompt("verifier")


def build_verifier_view(
    normalized: NormalizedInput,
    deterministic_result: VerificationResult,
) -> VerifierInputView:
    """Build the compact prompt payload for semantic verification."""
    excerpt, truncated = content_excerpt(normalized.content)
    metadata = deterministic_result.metadata

    return VerifierInputView(
        modality=normalized.modality,
        content_type=normalized.content_type,
        content_excerpt=excerpt,
        deterministic_categories=deterministic_result.categories,
        deterministic_score=int(metadata.get("deterministic_score", 0)),
        matched_rules=list(metadata.get("matched_rules", [])),
        excerpt_truncated=bool(metadata.get("excerpt_truncated", truncated)),
        sanitizer_summary=dict(metadata.get("sanitizer_summary", {})),
        target_provider=normalized.target_provider,
        target_model=normalized.target_model,
    )


def _coerce_consistent_llm_result(llm_result: VerifierLLMResult) -> VerifierLLMResult:
    """Repair inconsistent structured output conservatively."""
    threat_level = ThreatLevel(llm_result.threat_level)
    proceed = llm_result.proceed
    dangerous = llm_result.dangerous
    warn = llm_result.warn

    if threat_level.should_block:
        proceed = False
        dangerous = True
        warn = False
    elif threat_level.should_warn:
        proceed = True
        dangerous = False
        warn = True
    elif dangerous or not proceed:
        threat_level = ThreatLevel.HIGH
        proceed = False
        dangerous = True
        warn = False
    else:
        proceed = True
        dangerous = False
        warn = False

    return VerifierLLMResult(
        proceed=proceed,
        dangerous=dangerous,
        warn=warn,
        threat_level=threat_level.value,
        reason=llm_result.reason,
        categories=llm_result.categories,
    )


def _merge_result(
    normalized: NormalizedInput,
    deterministic_result: VerificationResult,
    llm_result: VerifierLLMResult,
) -> VerificationResult:
    """Merge semantic verifier output with deterministic routing metadata."""
    llm_result = _coerce_consistent_llm_result(llm_result)
    categories = sorted(set(deterministic_result.categories) | set(llm_result.categories))
    metadata = dict(deterministic_result.metadata)
    prompt = _verifier_prompt()
    metadata["llm_verifier"] = {
        "ran": True,
        "threat_level": llm_result.threat_level,
        "categories": llm_result.categories,
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
    }

    return verification_result(
        proceed=llm_result.proceed,
        dangerous=llm_result.dangerous,
        warn=llm_result.warn,
        threat_level=ThreatLevel(llm_result.threat_level),
        reason=llm_result.reason or deterministic_result.reason,
        categories=categories,
        routing_action=deterministic_result.routing_action,
        normalized=normalized,
        metadata=metadata,
    )


async def verify_with_llm(
    normalized: NormalizedInput,
    deterministic_result: VerificationResult,
) -> VerificationResult:
    """Run semantic verifier classification and return merged result."""
    view = build_verifier_view(normalized, deterministic_result)
    prompt = view.model_dump_json()

    # The framework adapter owns the SDK call, transient retries, usage limits, and
    # error translation. Config faults (e.g. a broken prompt) surface as VrakshaError
    # and propagate; any other provider failure becomes ModelUnavailableError. Either
    # way verifier.run still fails closed.
    handle = build_agent(
        "verifier",
        output_type=VerifierLLMResult,
        prompt_name="verifier",
        retries=constants.VERIFIER_MAX_RETRIES,
    )
    llm_result = await run_structured(handle, prompt)

    return _merge_result(normalized, deterministic_result, llm_result)
