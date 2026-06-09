"""
The capability store: holds every registered tool/expert by (kind, key).

OK capabilities are offered to the orchestrator (via catalog/cards); broken ones
are kept with their reason so brokenness is always visible, never silent. The
module-level `registry` is the process-wide singleton everything shares.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from .specs import CapabilityKind, CapabilitySpec, CapabilityStatus

log = logging.getLogger(__name__)


class CapabilityRegistry:
    """Holds every registered tool/expert by (kind, key). OK ones are offered;
    broken ones are kept with their reason so brokenness is visible, never silent."""

    def __init__(self) -> None:
        self._ok: dict[tuple[CapabilityKind, str], CapabilitySpec] = {}
        self._broken: dict[tuple[CapabilityKind, str], CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec, reason: str | None = None) -> CapabilitySpec:
        """Register a capability; `reason` (or a duplicate key) marks it BROKEN."""
        slot = (spec.kind, spec.key)
        if reason is None and slot in self._ok:
            reason = f"duplicate key {spec.key!r} for {spec.kind.value}"
        if reason is not None:
            broken = replace(spec, status=CapabilityStatus.BROKEN, reason=reason)
            self._broken[slot] = broken
            log.warning("capability registered BROKEN: %s — %s", spec.key, reason)
            return broken
        self._ok[slot] = spec
        return spec

    def get_tool(self, key: str) -> CapabilitySpec | None:
        return self._ok.get((CapabilityKind.TOOL, key))

    def get_expert(self, key: str) -> CapabilitySpec | None:
        return self._ok.get((CapabilityKind.EXPERT, key))

    def catalog(self, kind: CapabilityKind) -> list[dict]:
        """OK capabilities of a kind, as a compact list (key/description/domain/tags)."""
        return [
            {"key": s.key, "description": s.description, "domain": s.domain, "tags": list(s.tags)}
            for (k, _), s in self._ok.items()
            if k == kind
        ]

    def cards(self, kind: CapabilityKind) -> list[dict]:
        """
        Robust, machine-readable cards: each OK capability with its input JSON
        Schema (what to emit to call it) plus a status. The gateway uses these to
        build the orchestrator's native tools; broken capabilities are surfaced
        separately via `unavailable()`.
        """
        cards: list[dict] = []
        for (k, _), s in self._ok.items():
            if k != kind:
                continue
            cards.append({
                "key": s.key,
                "kind": s.kind.value,
                "description": s.description,
                "domain": s.domain,
                "tags": list(s.tags),
                "permission": s.permission.value,
                "input_schema": s.input_schema.model_json_schema() if s.input_schema else {},
                "status": "available",
            })
        return cards

    def unavailable(self, kind: CapabilityKind) -> list[dict]:
        """Broken capabilities of a kind: known to exist, not callable (with reason)."""
        return [
            {"key": s.key, "status": "broken", "reason": s.reason}
            for (k, _), s in self._broken.items()
            if k == kind
        ]

    def status(self, kind: CapabilityKind, key: str) -> tuple[CapabilityStatus, str | None] | None:
        """Status of a key: (OK, None), (BROKEN, reason), or None if unknown."""
        if (kind, key) in self._ok:
            return (CapabilityStatus.OK, None)
        broken = self._broken.get((kind, key))
        if broken is not None:
            return (CapabilityStatus.BROKEN, broken.reason)
        return None

    def describe_missing(self, kind: CapabilityKind, key: str) -> str:
        """Why a key isn't usable: broken (with reason) or unknown. Shared by handlers."""
        st = self.status(kind, key)
        if st is not None and st[0] == CapabilityStatus.BROKEN:
            return f"{kind.value} {key!r} is broken: {st[1]}"
        return f"unknown {kind.value} {key!r}"

    def broken(self) -> list[CapabilitySpec]:
        return list(self._broken.values())

    def reset(self) -> None:
        """Clear the registry (tests/tooling only)."""
        self._ok.clear()
        self._broken.clear()


registry = CapabilityRegistry()
