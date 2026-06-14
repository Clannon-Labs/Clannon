"""
How capabilities get registered: the `@tool` / `@expert` decorators (the only way
to register one) and `discover()` (imports the capability packages so the
decorators fire). Drop a decorated file under the root `tools/` or `experts/`
package and it self-registers — no wiring, for 1 capability or 100.

`enabled=False` skips registration; an enabled-but-malformed (or duplicate)
capability registers as BROKEN (recorded, logged, excluded) rather than crashing.
"""

from __future__ import annotations

import importlib
import pkgutil

from foundation import PermissionLevel

from .specs import CapabilityKind, ExpertSpec, ToolSpec, validate
from .store import registry

_CAPABILITY_PACKAGES = ("tools", "experts")


def tool(cls: type | None = None, *, enabled: bool = True) -> type:
    """
    Register a tool class. Use it bare (`@tool`) or with the enable toggle
    (`@tool(enabled=False)`); ALL other metadata lives on the class:
        name, domain, description, input_schema, output_schema   (required)
        permission (default READ), tags (default ())
    Identity key = f'{domain}.{name}'. A missing/invalid field registers BROKEN
    (recorded, excluded), never crashes.
    """
    def decorate(target: type) -> type:
        if not enabled:
            return target
        spec = ToolSpec(
            name=getattr(target, "name", ""),
            kind=CapabilityKind.TOOL,
            description=getattr(target, "description", ""),
            domain=getattr(target, "domain", ""),
            impl=target,
            tags=tuple(getattr(target, "tags", ())),
            permission=getattr(target, "permission", PermissionLevel.READ),
            input_schema=getattr(target, "input_schema", None),
            output_schema=getattr(target, "output_schema", None),
            timeout_s=getattr(target, "timeout_s", None),
        )
        registry.register(spec, validate(spec))
        return target

    # bare `@tool` -> cls is the class; `@tool(enabled=...)` -> cls is None.
    return decorate(cls) if cls is not None else decorate


def expert(cls: type | None = None, *, enabled: bool = True) -> type:
    """
    Register an expert class. Use it bare (`@expert`) or with the enable toggle
    (`@expert(enabled=False)`); ALL other metadata lives on the class:
        name, domain, description, input_schema, output_schema, skills  (required)
        tools (granted tool keys, default ()), model_role (default 'research'),
        permission (default READ), tags (default ())
    The system prompt is co-located (system.md beside the expert), not declared
    here. A missing/invalid field registers BROKEN, never crashes.
    """
    def decorate(target: type) -> type:
        if not enabled:
            return target
        spec = ExpertSpec(
            name=getattr(target, "name", ""),
            kind=CapabilityKind.EXPERT,
            description=getattr(target, "description", ""),
            domain=getattr(target, "domain", ""),
            impl=target,
            tags=tuple(getattr(target, "tags", ())),
            permission=getattr(target, "permission", PermissionLevel.READ),
            input_schema=getattr(target, "input_schema", None),
            output_schema=getattr(target, "output_schema", None),
            model_role=getattr(target, "model_role", "research"),
            tool_grants=tuple(getattr(target, "tools", ())),
            skills=tuple(getattr(target, "skills", ())),
        )
        registry.register(spec, validate(spec))
        return target

    return decorate(cls) if cls is not None else decorate


_discovered = False


def discover() -> None:
    """Import all tool/expert modules once (idempotent) so the decorators fire."""
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
