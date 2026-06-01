from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Type


# =========================================================
# Registry Kind
# =========================================================

class RegistryKind(str, Enum):
    """
    Defines the semantic execution category.

    TOOL:
        Stateless/direct execution primitive.

    EXPERT:
        Stateful reasoning unit that may use tools.
    """

    TOOL = "tool"
    EXPERT = "expert"


# =========================================================
# Registry Entry
# =========================================================

@dataclass(slots=True)
class RegistryEntry:
    """
    Canonical internal representation of a registered object.

    This is the SINGLE source of truth for registry state.

    Attributes
    ----------
    name:
        Stable semantic identity.

    domain:
        Namespace/grouping identifier.

    key:
        Globally unique registry identifier.
        Derived from:
            "{kind}.{domain}.{name}"

    kind:
        TOOL or EXPERT.

    tags:
        Optional routing metadata for orchestrator/LLM.

    enabled:
        Whether object is active.

    cls:
        Original class object.
    """

    name: str
    domain: str
    key: str
    kind: RegistryKind

    cls: Type

    enabled: bool = True

    tags: List[str] = field(default_factory=list)

