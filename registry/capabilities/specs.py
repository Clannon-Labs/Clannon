"""
Capability specs + validation.

A capability's identity is its derived `key` = ``f"{domain}.{name}"``, unique per
kind, so a bare "research" is never ambiguous and two capabilities can't claim
the same ability. `validate()` returns None for a well-formed spec or a short
reason string for a broken one (registered-but-excluded, never fatal).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from foundation import PermissionLevel


class CapabilityKind(str, Enum):
    TOOL = "tool"
    EXPERT = "expert"


class CapabilityStatus(str, Enum):
    OK = "ok"          # registered and offered to the orchestrator
    BROKEN = "broken"  # registered but excluded; reason recorded, never offered


@dataclass(frozen=True)
class CapabilitySpec:
    """Common description shared by tools and experts."""
    name: str
    kind: CapabilityKind
    description: str
    domain: str
    impl: Any                                   # the decorated class (exposes async run)
    tags: tuple[str, ...] = ()
    permission: PermissionLevel = PermissionLevel.READ
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    status: CapabilityStatus = CapabilityStatus.OK
    reason: str | None = None

    @property
    def key(self) -> str:
        """Domain-qualified identity, unique per kind."""
        return f"{self.domain}.{self.name}"


@dataclass(frozen=True)
class ToolSpec(CapabilitySpec):
    """A tool: fully described by the base fields + its impl."""
    timeout_s: float | None = None   # per-tool wall time; None = constants.TOOL_TIMEOUT_S


@dataclass(frozen=True)
class ExpertSpec(CapabilitySpec):
    """An expert: an agent with a co-located system prompt, skills, a model role,
    and scoped tools. Its prompt + skills live beside its code, not in a registry."""
    model_role: str = "research"
    tool_grants: tuple[str, ...] = ()   # tool keys this expert may call
    skills: tuple[str, ...] = ()        # .md files or folders beside the expert


def _is_pydantic(schema: object) -> bool:
    return isinstance(schema, type) and issubclass(schema, BaseModel)


def validate(spec: CapabilitySpec) -> str | None:
    """Return a reason string if the spec is broken, else None."""
    if not (spec.name or "").strip():
        return "missing name"
    if not (spec.description or "").strip():
        return "missing description"
    if not (spec.domain or "").strip():
        return "missing domain"
    if not inspect.iscoroutinefunction(getattr(spec.impl, "run", None)):
        return "must expose an async run() method"
    if not _is_pydantic(spec.output_schema):
        return "output_schema must be a pydantic BaseModel"
    # Both tools and experts are invoked with structured arguments validated
    # against this schema — never free-form text.
    if not _is_pydantic(spec.input_schema):
        return "requires an input_schema (pydantic BaseModel)"
    if spec.kind == CapabilityKind.EXPERT:
        if not getattr(spec, "skills", ()):
            return "expert requires at least one skill (a .md file or folder)"
    return None
