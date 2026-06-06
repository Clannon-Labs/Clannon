"""Deterministic verifier checks."""

from __future__ import annotations

from typing import Any

from foundation import (
    Flow,
    NormalizedInput,
    ThreatLevel,
    VerificationResult,
    VerifierError,
    load_model_registry,
)

from .constants import (
    KNOWN_MODALITIES,
    NATIVE_MODALITIES,
    ROUTING_BLOCK,
    ROUTING_DIRECT,
    ROUTING_EXPERT,
    TEXT_MODALITIES,
)
from .rules import scan_text_risk
from .utils import sanitizer_summary, verification_result


def verify_handoff(normalized: Any) -> VerificationResult | None:
    """
    Validate the normalized object shape.

    Returning None means the handoff is structurally coherent. Returning a
    VerificationResult means the input should be blocked as a user/request
    problem. Type/configuration faults are raised as VerifierError.
    """
    if not isinstance(normalized, NormalizedInput):
        raise VerifierError(
            f"Verifier expected NormalizedInput, got {type(normalized).__name__}"
        )

    if normalized.modality not in KNOWN_MODALITIES:
        return verification_result(
            proceed=False,
            dangerous=True,
            threat_level=ThreatLevel.HIGH,
            reason=f"Unsupported normalized modality: {normalized.modality}",
            categories=["unsupported_modality"],
            routing_action=ROUTING_BLOCK,
            normalized=normalized,
        )

    if normalized.preserved_native and normalized.requires_expert:
        raise VerifierError(
            "NormalizedInput cannot both preserve native media and require an expert"
        )

    if normalized.modality in TEXT_MODALITIES and not normalized.content:
        raise VerifierError(f"{normalized.modality} input reached verifier without content")

    if normalized.modality in NATIVE_MODALITIES and normalized.native_payload is None:
        raise VerifierError(f"{normalized.modality} input reached verifier without native_payload")

    if normalized.requires_expert and not normalized.required_capability:
        raise VerifierError("NormalizedInput requires expert but has no required_capability")

    if not normalized.content and normalized.native_payload is None:
        raise VerifierError("NormalizedInput has neither content nor native_payload")

    return None


def verify_routing(normalized: NormalizedInput) -> VerificationResult | None:
    """
    Validate target model capability and routing flags.

    The verifier does not select experts. It only confirms whether the
    normalizer's direct/native or expert-routing decision is coherent.
    """
    registry = load_model_registry()
    target_layer = normalized.target_layer or "orchestrator"
    target_model = registry.for_layer(target_layer, provider=normalized.target_provider)

    if normalized.target_model and normalized.target_model != target_model.model:
        raise VerifierError(
            "NormalizedInput target model does not match registry: "
            f"{normalized.target_model} != {target_model.model}"
        )

    supports_modality = target_model.supports(normalized.modality)

    if normalized.modality in TEXT_MODALITIES:
        return None

    if normalized.preserved_native and not supports_modality:
        raise VerifierError(
            f"{target_layer} target model does not support preserved {normalized.modality}"
        )

    if normalized.requires_expert:
        if supports_modality:
            raise VerifierError(
                f"{target_layer} target model supports {normalized.modality}, "
                "but normalized input requires an expert"
            )

        if not registry.capable_profiles(normalized.required_capability or normalized.modality):
            return verification_result(
                proceed=False,
                dangerous=False,
                threat_level=ThreatLevel.HIGH,
                reason=(
                    "No configured expert/model supports required capability: "
                    f"{normalized.required_capability or normalized.modality}"
                ),
                categories=["unsupported_modality"],
                routing_action=ROUTING_BLOCK,
                normalized=normalized,
            )

    return None


def verify_deterministic(flow: Flow[Any], normalized: Any) -> VerificationResult:
    """Run all deterministic verifier checks and return a structured result."""
    handoff_result = verify_handoff(normalized)
    if handoff_result:
        return handoff_result

    assert isinstance(normalized, NormalizedInput)

    routing_result = verify_routing(normalized)
    if routing_result:
        return routing_result

    if normalized.modality in TEXT_MODALITIES:
        result = scan_text_risk(normalized)
    else:
        routing_action = ROUTING_EXPERT if normalized.requires_expert else ROUTING_DIRECT
        result = verification_result(
            proceed=True,
            routing_action=routing_action,
            normalized=normalized,
            metadata={"native_media_verified": True},
        )

    result.metadata["sanitizer_summary"] = sanitizer_summary(flow)
    return result
