"""
Foundation public surface.

This is the only import seam the rest of Vraksha uses: `from foundation import X`.
Internals are organised into buckets (transport/, vocab/, contracts/, plus
coercion at the root), but callers should never reach into those paths directly —
import the name here.
"""

# transport — the fiber
from .transport.flow import Flow, PayloadHandle, JournalEntry
from .transport.primitives import Status, Meta
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
    MemoryTurn,
    MemoryWriteProposal,
    MemoryPort,
)
from .contracts.graph import (
    NodeLabel,
    EdgeLabel,
    EdgeOrigin,
    GraphScope,
    GraphNode,
    GraphEdge,
    GraphResult,
    GraphPort,
)
from .contracts.budget import (
    BudgetScope,
    TokenBudget,
    BudgetReservation,
    BudgetPort,
)
from .contracts.batch_awareness import (
    BatchAwarenessItem,
    CrossBatchAwareness,
    BatchAwarenessPort,
)
from .contracts.workspace import RunResult, WorkspacePort
from .contracts.artifact import ArtifactRef, ArtifactStore
from .contracts.mailer import Accepted, MailError, Mailer, Message
from .contracts.input_file import InputFile

# payload boundary
from .coercion import coerce_to_bytes

# project root
from .paths import get_root

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
    BudgetExhausted,
    SandboxError,
    ConfigError,
)
from .vocab.types import (
    Modality,
    ThreatLevel,
    BlockReason,
    PermissionLevel,
    MemoryStore,
    MemoryKind,
    MemorySaver,
    Origin,
    BatchLifecycleStatus,
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
    "MemoryTurn",
    "MemoryWriteProposal",
    "MemoryPort",
    "NodeLabel",
    "EdgeLabel",
    "EdgeOrigin",
    "GraphScope",
    "GraphNode",
    "GraphEdge",
    "GraphResult",
    "GraphPort",
    "BudgetScope",
    "TokenBudget",
    "BudgetReservation",
    "BudgetPort",
    "BatchLifecycleStatus",
    "BatchAwarenessItem",
    "CrossBatchAwareness",
    "BatchAwarenessPort",
    "RunResult",
    "WorkspacePort",
    "ArtifactRef",
    "ArtifactStore",
    "Accepted",
    "MailError",
    "Mailer",
    "Message",
    "InputFile",
    "coerce_to_bytes",
    "get_root",

    # transport primitives (used inside flow, available if needed directly)
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
    "BudgetExhausted",
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
    "MemoryKind",
    "MemorySaver",
    "Origin",

    # constants (always import as module)
    "constants",
]
