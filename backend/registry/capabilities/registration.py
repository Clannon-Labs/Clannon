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
import logging
import pkgutil

from foundation import PermissionLevel

from .specs import CapabilityKind, ExpertSpec, ToolSpec, validate
from .store import registry

log = logging.getLogger(__name__)

_CAPABILITY_PACKAGES = ("tools", "experts")

# Owner-approved private-alpha policy. These capabilities are deliberately absent
# from registry discovery, so prompt text, model output, and direct key calls cannot
# authorize external mutation. Re-enabling one is a code-reviewed policy change,
# not an environment toggle or prompt edit.
PRIVATE_ALPHA_DENIED_TOOL_KEYS = frozenset({"http.request"})
PRIVATE_ALPHA_DENIED_EXPERT_KEYS = frozenset({"delivery.notifier"})
PRIVATE_ALPHA_DENIED_KEYS = PRIVATE_ALPHA_DENIED_TOOL_KEYS | PRIVATE_ALPHA_DENIED_EXPERT_KEYS

# (module_name, error) for capability modules that raised AT IMPORT time during
# discover(). Surfaced via import_failures() so a skipped module is visible, not
# silent — the import-time analogue of the registry's BROKEN (malformed-metadata) list.
_import_failures: list[tuple[str, str]] = []


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
            eager=getattr(target, "eager", False),
            timeout_s=getattr(target, "timeout_s", None),
        )
        if spec.key in PRIVATE_ALPHA_DENIED_TOOL_KEYS:
            return target
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
            eager=getattr(target, "eager", False),
            model_role=getattr(target, "model_role", "research"),
            tool_grants=tuple(getattr(target, "tools", ())),
            skills=tuple(getattr(target, "skills", ())),
        )
        if spec.key in PRIVATE_ALPHA_DENIED_EXPERT_KEYS:
            return target
        registry.register(spec, validate(spec))
        return target

    return decorate(cls) if cls is not None else decorate


_discovered = False


def discover() -> None:
    """Import all tool/expert modules once (idempotent) so the decorators fire.

    A single capability module that raises AT IMPORT time (top-level error, bad
    dependency, syntax error) is logged, recorded in `import_failures()`, and
    SKIPPED — it must never take down the rest of the roster. This is the registry's
    core invariant ("a broken capability is recorded and excluded, never fatal")
    applied at import time; decorator-time validation (malformed metadata) is handled
    separately via the BROKEN registry. A batch layer dropping in new capability
    modules relies on exactly this isolation."""
    global _discovered
    if _discovered:
        return
    for package_name in _CAPABILITY_PACKAGES:
        package = importlib.import_module(package_name)
        for module in pkgutil.walk_packages(package.__path__, prefix=package.__name__ + "."):
            try:
                importlib.import_module(module.name)
            except Exception as exc:  # noqa: BLE001 — one bad module must not sink discovery
                log.warning("capability module %s failed to import (skipped): %s", module.name, exc)
                _import_failures.append((module.name, str(exc)))
    _discovered = True


def import_failures() -> list[tuple[str, str]]:
    """(module, error) for capability modules that failed to import during discover().
    Empty on a clean roster; a non-empty list means those modules were skipped."""
    return list(_import_failures)


def reset_discovery() -> None:
    """Allow re-discovery (tests/tooling only)."""
    global _discovered
    _discovered = False
    _import_failures.clear()
