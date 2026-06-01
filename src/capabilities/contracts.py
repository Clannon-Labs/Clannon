from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any, Literal
from uuid import uuid4

ActorKind = Literal["agent", "expert", "broker", "tool", "system"]


@dataclass(slots=True, frozen=True)
class Actor:
    kind: ActorKind
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "name": self.name}


@dataclass(slots=True, frozen=True)
class Usage:
    cost_units: int = 0
    input_bytes: int = 0
    output_bytes: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "cost_units": self.cost_units,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(slots=True, frozen=True)
class ErrorInfo:
    code: str
    message: str
    retryable: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(slots=True, frozen=True)
class CapabilityRequest:
    capability: str
    arguments: dict[str, Any]
    reason: str
    caller: Actor
    request_id: str = field(default_factory=lambda: uuid4().hex)
    parent_id: str | None = None
    budget_units: int | None = None
    timeout_ms: int | None = None
    created_ns: int = field(default_factory=monotonic_ns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "parent_id": self.parent_id,
            "capability": self.capability,
            "arguments": self.arguments,
            "reason": self.reason,
            "caller": self.caller.to_dict(),
            "budget_units": self.budget_units,
            "timeout_ms": self.timeout_ms,
            "created_ns": self.created_ns,
        }


@dataclass(slots=True, frozen=True)
class CapabilityResult:
    request_id: str
    success: bool
    data: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    usage: Usage = field(default_factory=Usage)

    @classmethod
    def ok(
        cls,
        request: CapabilityRequest,
        data: dict[str, Any] | None = None,
        usage: Usage | None = None,
    ) -> CapabilityResult:
        return cls(
            request_id=request.request_id,
            success=True,
            data=data or {},
            error=None,
            usage=usage or Usage(),
        )

    @classmethod
    def fail(
        cls,
        request: CapabilityRequest,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        usage: Usage | None = None,
    ) -> CapabilityResult:
        return cls(
            request_id=request.request_id,
            success=False,
            data=None,
            error=ErrorInfo(code=code, message=message, retryable=retryable),
            usage=usage or Usage(),
        )

    def to_tool_output(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": None if self.error is None else self.error.message,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "success": self.success,
            "data": self.data,
            "error": None if self.error is None else self.error.to_dict(),
            "usage": self.usage.to_dict(),
        }
