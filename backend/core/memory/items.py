"""Translate store payloads into the neutral ``foundation.MemoryItem`` shape."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from foundation import MemoryItem, MemoryKind, MemorySaver, MemoryStore

from .tiers import TIER_TRUST


def _coerce_kind(raw: object) -> MemoryKind:
    """Legacy or malformed payloads stay honestly untyped."""
    try:
        return MemoryKind(raw)
    except (TypeError, ValueError):
        return MemoryKind.UNSPECIFIED


def _coerce_saver(raw: object) -> MemorySaver:
    """Legacy or malformed payloads stay honestly unattributed."""
    try:
        return MemorySaver(raw)
    except (TypeError, ValueError):
        return MemorySaver.UNSPECIFIED


def _float(raw: object) -> float:
    """Malformed legacy metadata must not fail hydration/listing."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _int(raw: object, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _text(raw: object) -> str:
    return "" if raw is None else str(raw)


def from_payload(
    tier: MemoryStore,
    payload: Mapping[str, Any],
    *,
    score: float | None = None,
) -> MemoryItem:
    """Build one contract item from a tenant-checked store payload."""
    return MemoryItem(
        store=tier,
        content=_text(payload.get("content", "")),
        memory_id=_text(payload.get("id", "")),
        score=_float(payload.get("score", 0.0) if score is None else score),
        trust=_int(payload.get("trust", TIER_TRUST[tier]), TIER_TRUST[tier]),
        created_at=_float(payload.get("created_at", 0.0)),
        rationale=_text(payload.get("rationale", "")),
        confidence=_float(payload.get("confidence", 0.0)),
        session_id=_text(payload.get("session_id", "")),
        trace_id=_text(payload.get("trace_id", "")),
        saved_by=_coerce_saver(payload.get("saved_by")),
        kind=_coerce_kind(payload.get("kind")),
        valid_at=_float(payload.get("valid_at", 0.0)),
        source=_text(payload.get("source", "")),
        superseded_by=_text(payload.get("superseded_by", "")),
        participants=_text(payload.get("participants", "")),
    )
