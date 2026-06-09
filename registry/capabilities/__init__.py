"""
Unified capability registry for tools and experts.

Drop a `@tool`/`@expert`-decorated file under tools/ or experts/ and it
self-registers — no wiring, for 1 capability or 100. `enabled=False` skips
registration; an enabled-but-malformed (or duplicate) capability registers as
BROKEN (recorded, logged, excluded from the catalog) rather than crashing the
app. `discover()` imports the capability packages so the decorators fire.

This whole mechanism lives in two files: `specs.py` (what a capability is +
validation) and this one (the store, decorators, and discovery).
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import replace
from typing import Callable

from pydantic import BaseModel

from foundation import PermissionLevel

from .specs import (
    CapabilityKind,
    CapabilitySpec,
    CapabilityStatus,
    ExpertSpec,
    ToolSpec,
    validate,
)

log = logging.getLogger(__name__)

_CAPABILITY_PACKAGES = ("core.orchestrator.tools", "core.orchestrator.experts")


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

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
        """OK capabilities of a kind, as the advisor-facing catalog."""
        return [
            {"key": s.key, "description": s.description, "domain": s.domain, "tags": list(s.tags)}
            for (k, _), s in self._ok.items()
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


# ---------------------------------------------------------------------------
# Decorators — the only way to register a capability
# ---------------------------------------------------------------------------

def tool(
    *,
    name: str,
    description: str,
    domain: str,
    input_schema: type[BaseModel],
    output_schema: type[BaseModel],
    tags: tuple[str, ...] = (),
    permission: PermissionLevel = PermissionLevel.READ,
    enabled: bool = True,
) -> Callable[[type], type]:
    """Register a tool class. Identity key = f'{domain}.{name}'."""
    def decorate(cls: type) -> type:
        if not enabled:
            return cls
        spec = ToolSpec(
            name=name, kind=CapabilityKind.TOOL, description=description, domain=domain,
            impl=cls, tags=tuple(tags), permission=permission,
            input_schema=input_schema, output_schema=output_schema,
        )
        registry.register(spec, validate(spec))
        return cls
    return decorate


def expert(
    *,
    name: str,
    description: str,
    domain: str,
    prompt_name: str,
    output_schema: type[BaseModel],
    skills: tuple[str, ...] = (),
    tools: tuple[str, ...] = (),
    model_role: str = "research",
    tags: tuple[str, ...] = (),
    permission: PermissionLevel = PermissionLevel.READ,
    enabled: bool = True,
) -> Callable[[type], type]:
    """Register an expert class. Needs a prompt and >=1 skill to be eligible."""
    def decorate(cls: type) -> type:
        if not enabled:
            return cls
        spec = ExpertSpec(
            name=name, kind=CapabilityKind.EXPERT, description=description, domain=domain,
            impl=cls, tags=tuple(tags), permission=permission, output_schema=output_schema,
            model_role=model_role, prompt_name=prompt_name,
            tool_grants=tuple(tools), skills=tuple(skills),
        )
        registry.register(spec, validate(spec))
        return cls
    return decorate


# ---------------------------------------------------------------------------
# Discovery — import capability modules so the decorators fire
# ---------------------------------------------------------------------------

_discovered = False


def discover() -> None:
    """Import all tool/expert modules once (idempotent)."""
    global _discovered
    if _discovered:
        return
    for package_name in _CAPABILITY_PACKAGES:
        package = importlib.import_module(package_name)
        for module in pkgutil.walk_packages(package.__path__, prefix=package.__name__ + "."):
            importlib.import_module(module.name)
    _discovered = True


def reset_discovery() -> None:
    """Allow re-discovery (tests/tooling only)."""
    global _discovered
    _discovered = False


__all__ = [
    "CapabilityKind",
    "CapabilityStatus",
    "CapabilitySpec",
    "ToolSpec",
    "ExpertSpec",
    "CapabilityRegistry",
    "registry",
    "tool",
    "expert",
    "validate",
    "discover",
    "reset_discovery",
]
