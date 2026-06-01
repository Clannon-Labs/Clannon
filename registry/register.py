"""Decorator-first registration for Vraksha tools and experts.

Capability authors should only have to import ``tool`` or ``expert`` from this
module. The registry owns repetitive metadata defaults, validation, canonical
key generation, and runtime metadata attachment so individual tools and experts
can stay small.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type

from registry.base import RegistryKind, RegistryEntry
from registry.validate import Validator
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA

# =========================================================
# Registry
# =========================================================

class Registry:
    """
    Central plugin registry for:
        - tools
        - experts

    Architecture
    ------------
    Registry keys are globally unique.

    Example:
        tool.web.search
        expert.finance.risk_analyzer

    Internal Structure
    ------------------
    Registry stores flat mappings:

        {
            "tool.web.search": RegistryEntry(...)
        }

    This avoids:
        - nested traversal
        - namespace collisions
        - lookup complexity

    Public API
    ----------
    Use:
        @tool(...)
        @expert(...)

    Users NEVER interact with Registry directly.
    """

    # str: Our unique key (eg: tool.web.search)
    _registry: Dict[str, RegistryEntry] = {}

    
    # =====================================================
    # Registration
    # =====================================================

    @staticmethod
    def _register(
        *,
        cls: Type,
        kind: RegistryKind,
        enabled: bool,
        domain: str,
        tags: Optional[List[str]] = None,
    ) -> Type:
        """
        Normalize, validate, and store one decorated capability class.

        Tool and expert authors should only need to import ``tool`` or
        ``expert`` from this module. To keep that public surface small, this
        method fills in predictable defaults before validation:

        * ordinary tools/experts may omit ``output_schema``.
        * primitive tools must provide the complete explicit contract.
        * expert ``instruction_files`` defaults to a sibling ``SKILL.md``.

        Validation still runs after normalization, so missing meaningful expert
        instructions or malformed schemas fail early during discovery.
        """

        # -------------------------------------------------
        # Domain validation
        # -------------------------------------------------

        if not isinstance(domain, str):
            raise TypeError("domain must be str")

        if not domain.strip():
            raise ValueError("domain cannot be empty")

        # normalize
        domain = domain.strip().lower()

        # -------------------------------------------------
        # Tags normalization
        # -------------------------------------------------

        tags = tags or []

        if not isinstance(tags, list):
            raise TypeError("tags must be List[str]")

        for tag in tags:
            if not isinstance(tag, str):
                raise TypeError(
                    "all tags must be str"
                )

        _apply_registration_defaults(cls, kind, tags)

        if kind == RegistryKind.TOOL:
            Validator.validate_tool(cls)

        elif kind == RegistryKind.EXPERT:
            Validator.validate_expert(cls)

        else:
            raise ValueError(
                f"Unknown registry kind: {kind}"
            )

        # -------------------------------------------------
        # Generate canonical key
        # -------------------------------------------------

        # Creates a key like tool.web.search
        key = f"{kind.value}.{domain}.{cls.name}"

        # -------------------------------------------------
        # Prevent duplicates
        # -------------------------------------------------

        if key in Registry._registry:
            raise ValueError(
                f"Duplicate registry key detected: {key}"
            )

        # -------------------------------------------------
        # Attach runtime metadata
        # -------------------------------------------------

        setattr(cls, "__registry_key__", key)
        setattr(cls, "__registry_kind__", kind)
        setattr(cls, "__registry_domain__", domain)
        setattr(cls, "__registry_tags__", tags)

        # -------------------------------------------------
        # Create entry
        # -------------------------------------------------

        entry = RegistryEntry(
            name=cls.name,
            domain=domain,
            key=key,
            kind=kind,
            cls=cls,
            enabled=enabled,
            tags=tags,
        )

        # -------------------------------------------------
        # Store
        # -------------------------------------------------

        Registry._registry[key] = entry

        return cls

    # =====================================================
    # Access Helpers
    # =====================================================

    @staticmethod
    def get(key: str) -> Optional[RegistryEntry]:
        """
        Retrieve registry entry by canonical key.

        This is mainly used by the broker and tests. Capability authors should
        not need it when defining new tools or experts.
        """

        return Registry._registry.get(key)

    @staticmethod
    def all() -> Dict[str, RegistryEntry]:
        """
        Return all registered entries.

        The registry intentionally returns the live mapping for internal
        bootstrapping code. Tests may clear or restore it, but ordinary
        capability code should not mutate this dictionary.
        """

        return Registry._registry

    @staticmethod
    def tools() -> Dict[str, RegistryEntry]:
        """
        Return all registered tools currently registered in memory.
        """

        return {
            k: v
            for k, v in Registry._registry.items()
            if v.kind == RegistryKind.TOOL
        }

    @staticmethod
    def experts() -> Dict[str, RegistryEntry]:
        """
        Return all registered experts currently registered in memory.
        """

        return {
            k: v
            for k, v in Registry._registry.items()
            if v.kind == RegistryKind.EXPERT
        }


# =========================================================
# Public Decorators
# =========================================================

def tool(
    *,
    enabled: bool = True,
    domain: str,
    tags: Optional[List[str]] = None,
) -> Callable:
    """
    Public decorator for deterministic tool registration.

    Authors only need to import this decorator from ``registry.register``.
    Basic tools provide their ``name``, ``description``, ``input_schema``, and
    ``call`` implementation. The registry supplies the standard
    ``output_schema`` unless the tool is tagged as ``primitive``.

    Minimal example:

    @tool(domain="demo")
    class Echo:
        name = "echo"
        description = "Return text unchanged."
        input_schema = {...}

        def call(self, tool_input: dict):
            return {"success": True, "data": tool_input, "error": None}
    """
    def decorator(cls: Type):
        """Register the class unless the decorator is explicitly disabled."""
        if not enabled:
            return cls

        return Registry._register(
            cls=cls,
            kind=RegistryKind.TOOL,
            enabled=enabled,
            domain=domain,
            tags=tags,
        )

    return decorator


def expert(
    *,
    enabled: bool = True,
    domain: str,
    tags: Optional[List[str]] = None,
) -> Callable:
    """
    Public decorator for reasoning expert registration.

    Like ``tool``, this decorator keeps the authoring surface intentionally
    small. Experts still provide their identity, input schema, and behavior.
    If ``instruction_files`` is omitted and a ``SKILL.md`` lives beside the
    expert module, that file is attached automatically.

    Minimal example:

    @expert(domain="review")
    class ReviewExpert:
        name = "review"
        description = "Review proposed changes for correctness and risk."
        input_schema = {...}

        def call(self, tool_input: dict):
            return {"success": True, "data": {"notes": []}, "error": None}
    """
    def decorator(cls: Type):
        """Register the expert class unless the decorator is disabled."""
        if not enabled:
            return cls

        return Registry._register(
            cls=cls,
            kind=RegistryKind.EXPERT,
            enabled=enabled,
            domain=domain,
            tags=tags,
        )

    return decorator


def _apply_registration_defaults(
    cls: Type,
    kind: RegistryKind,
    tags: list[str],
) -> None:
    """Attach registry-owned defaults before strict validation runs.

    Basic capabilities may omit the standard output envelope because it is a
    system-wide contract. Primitive tools are stricter: they must provide their
    own output schema so their handler contract is explicit at the capability
    boundary. Explicit author-provided values always win.
    """
    if not _is_primitive_tool(kind, tags) and not hasattr(cls, "output_schema"):
        setattr(cls, "output_schema", dict(STANDARD_OUTPUT_SCHEMA))

    if kind == RegistryKind.EXPERT and not hasattr(cls, "instruction_files"):
        inferred = _infer_instruction_files(cls)
        if inferred:
            setattr(cls, "instruction_files", inferred)


def _is_primitive_tool(kind: RegistryKind, tags: list[str]) -> bool:
    """Return true when a tool opts into the stricter primitive contract."""
    return kind == RegistryKind.TOOL and "primitive" in tags


def _infer_instruction_files(cls: Type) -> list[str]:
    """Infer a sibling ``SKILL.md`` path for an expert class when it exists."""
    module = inspect.getmodule(cls)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return []

    skill_file = Path(module_file).resolve().parent / "SKILL.md"
    if not skill_file.exists():
        return []

    try:
        return [skill_file.relative_to(Path.cwd()).as_posix()]
    except ValueError:
        return [skill_file.as_posix()]
