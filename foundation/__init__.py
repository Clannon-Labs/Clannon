"""
Foundation public surface.

This is the only import seam the rest of Vraksha uses: `from foundation import X`.
Internals are organised into buckets (transport/, vocab/, contracts/, config/),
but callers should never reach into those paths directly — import the name here.
"""

# transport — the fiber
from .transport.flow import Flow, PayloadHandle, JournalEntry
from .transport.primitives import Envelope, Status, Meta
from .transport.context import (
    VrakshaContext,
    PipelineStage,
    ToolCallRecord,
    ExpertCallRecord,
)

# contracts — cross-layer/cross-stage shapes
from .contracts.payloads import NormalizedInput, OrchestratorResponse
from .contracts.memory import (
    MemoryItem,
    HydrationRequest,
    HydrationPackage,
    MemoryWriteProposal,
    MemoryPort,
)

# payload boundary
from .coercion import coerce_to_bytes

# vocab — shared declarations
from .vocab.errors import (
    VrakshaError,

    # 1xx
    InputError,
    UnsupportedModalityError,
    InputTooLargeError,
    MalformedInputError,

    # 2xx
    SecurityError,
    SanitizationError,
    VerifierError,
    FilterError,
    InjectionDetectedError,

    # 3xx
    OrchestratorError,
    ToolError,
    ExpertError,
    ToolNotPermittedError,
    ExpertNotPermittedError,
    MaxRetriesExceededError,

    # 4xx
    InfrastructureError,
    ModelUnavailableError,
    MemoryStoreError,
    CircuitOpenError,
    SandboxError,
    ConfigError,
)
from .vocab.types import (
    Modality,
    ThreatLevel,
    BlockReason,
    PermissionLevel,
    MemoryStore,
    ExpertState,
    Origin,
)
from .vocab import constants

__all__ = [
    # flow — the primary transport (this is what stages import)
    "Flow",
    "PayloadHandle",
    "JournalEntry",
    "NormalizedInput",
    "OrchestratorResponse",
    "MemoryItem",
    "HydrationRequest",
    "HydrationPackage",
    "MemoryWriteProposal",
    "MemoryPort",
    "coerce_to_bytes",

    # transport primitives (used inside flow, available if needed directly)
    "Envelope",
    "Status",
    "Meta",

    # errors — 1xx
    "VrakshaError",
    "InputError",
    "UnsupportedModalityError",
    "InputTooLargeError",
    "MalformedInputError",

    # errors — 2xx
    "SecurityError",
    "SanitizationError",
    "VerifierError",
    "FilterError",
    "InjectionDetectedError",

    # errors — 3xx
    "OrchestratorError",
    "ToolError",
    "ExpertError",
    "ToolNotPermittedError",
    "ExpertNotPermittedError",
    "MaxRetriesExceededError",

    # errors — 4xx
    "InfrastructureError",
    "ModelUnavailableError",
    "MemoryStoreError",
    "CircuitOpenError",
    "SandboxError",
    "ConfigError",

    # context
    "VrakshaContext",
    "PipelineStage",
    "ToolCallRecord",
    "ExpertCallRecord",

    # types
    "Modality",
    "ThreatLevel",
    "BlockReason",
    "PermissionLevel",
    "MemoryStore",
    "ExpertState",
    "Origin",

    # constants (always import as module)
    "constants",
]
