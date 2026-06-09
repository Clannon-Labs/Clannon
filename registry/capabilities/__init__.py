"""
Capability layer public surface: specs, invocation contracts, the store, and the
registration entry points. Pure imports/exports — the logic lives in specs.py,
schemas.py, store.py, and registration.py.

Drop a `@tool`/`@expert`-decorated file under the root tools/ or experts/ package
and it self-registers; `discover()` imports them so the decorators fire.
"""

from .specs import (
    CapabilityKind,
    CapabilitySpec,
    CapabilityStatus,
    ExpertSpec,
    ToolSpec,
    validate,
)
from .schemas import (
    ExpertFindings,
    ExpertOutput,
    ExpertRequest,
    ExpertSummary,
    ToolRequest,
)
from .store import CapabilityRegistry, registry
from .registration import discover, expert, reset_discovery, tool

__all__ = [
    # specs
    "CapabilityKind",
    "CapabilityStatus",
    "CapabilitySpec",
    "ToolSpec",
    "ExpertSpec",
    "validate",
    # store
    "CapabilityRegistry",
    "registry",
    # registration
    "tool",
    "expert",
    "discover",
    "reset_discovery",
    # invocation contracts (what to emit to call a capability + what it returns)
    "ToolRequest",
    "ExpertRequest",
    "ExpertSummary",
    "ExpertFindings",
    "ExpertOutput",
]
