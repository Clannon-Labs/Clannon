from .flow import Flow, PayloadHandle, JournalEntry
from .pillars.transport import Envelope, Status, Meta

from .pillars.errors import (
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
    MemoryError,
    CircuitOpenError,
    SandboxError,
    ConfigError,
)

from .pillars.context import VrakshaContext, PipelineStage, ToolCallRecord, ExpertCallRecord
from .pillars.types import (
    Modality,
    ThreatLevel,
    BlockReason,
    PermissionLevel,
    MemoryStore,
    ExpertState,
    Origin,
)
from . import constants

__all__ = [
    # flow — the primary transport (this is what stages import)
    "Flow",
    "PayloadHandle",
    "JournalEntry",

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
    "MemoryError",
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
