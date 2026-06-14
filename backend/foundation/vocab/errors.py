"""
foundation/vocab/errors.py

Structured exception taxonomy for Vraksha.
Every raise in the codebase uses one of these — never a bare Exception,
never a generic ValueError, never a raw RuntimeError.

Taxonomy (mirrors HTTP status code logic):
  1xx — Input errors       (what the user sent was the problem)
  2xx — Security errors    (threat detected or security layer fault)
  3xx — Orchestrator errors (reasoning loop or invocation fault)
  4xx — Infrastructure errors (deps, models, memory unavailable)

Reading a traceback tells you immediately which layer failed
without reading the exception message.

Usage:
    from foundation import VrakshaError, SanitizationError, VerifierError ...

    raise SanitizationError("malicious macro in pdf", trace_id=flow.meta.trace_id)

    try:
        ...
    except ModelUnavailableError as e:
        return flow.fail(e, Origin.VERIFIER)
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class VrakshaError(Exception):
    """
    Base class for all Vraksha exceptions.

    All errors carry:
      trace_id — the request trace they belong to, if available.
                 pass this from env.meta.trace_id so logs correlate.
      cause    — the original exception, if this wraps one.
    """
    def __init__(
        self,
        message: str,
        trace_id: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.trace_id = trace_id
        self.cause = cause

    def __str__(self) -> str:
        base = super().__str__()
        parts = [base]
        if self.trace_id:
            parts.append(f"trace_id={self.trace_id[:8]}")
        if self.cause:
            parts.append(f"caused_by={type(self.cause).__name__}: {self.cause}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# 1xx — Input errors
# The user or the incoming data is the problem.
# These are expected, not alarming. Log at INFO level.
# ---------------------------------------------------------------------------

class InputError(VrakshaError):
    """Base for all input-layer errors."""


class UnsupportedModalityError(InputError):
    """
    Input contains a file type or modality we don't handle.
    Example: user sends a .exe or an unknown binary format.
    """


class InputTooLargeError(InputError):
    """
    Input exceeds configured size limits.
    Check constants.py: MAX_INPUT_SIZE_BYTES, MAX_INPUT_TOKENS.
    """


class MalformedInputError(InputError):
    """
    Input arrived in a shape we can't parse at all.
    Example: claimed to be a PDF but failed basic structure check.
    """


# ---------------------------------------------------------------------------
# 2xx — Security errors
# Threat detected, or the security layer itself failed.
# BLOCKED errors: expected, log at WARNING.
# Layer faults: unexpected, log at ERROR.
# ---------------------------------------------------------------------------

class SecurityError(VrakshaError):
    """Base for all security-layer errors."""


class SanitizationError(SecurityError):
    """
    A sanitization worker detected a threat or failed to process input.

    If threat detected:   status=BLOCKED, log at WARNING
    If worker crashed:    status=ERROR,   log at ERROR

    Carry which modality and which worker flagged it:
        raise SanitizationError(
            "embedded JS in PDF",
            trace_id=...,
            modality="pdf",
            worker="pdfid"
        )
    """
    def __init__(
        self,
        message: str,
        trace_id: str | None = None,
        cause: BaseException | None = None,
        modality: str | None = None,
        worker: str | None = None,
    ) -> None:
        super().__init__(message, trace_id, cause)
        self.modality = modality
        self.worker = worker

    def __str__(self) -> str:
        base = super().__str__()
        parts = [base]
        if self.modality:
            parts.append(f"modality={self.modality}")
        if self.worker:
            parts.append(f"worker={self.worker}")
        return " | ".join(parts)


class VerifierError(SecurityError):
    """
    The verifier LLM rejected input or failed to produce a valid response.

    If input rejected:         status=BLOCKED
    If LLM output malformed:   status=ERROR (verifier itself is broken)
    """


class FilterError(SecurityError):
    """
    The output filter LLM rejected the orchestrator's response or failed.

    If output rejected:        status=BLOCKED (sent back to orchestrator)
    If LLM output malformed:   status=ERROR
    """


class InjectionDetectedError(SecurityError):
    """
    Prompt injection detected in input, tool result, or expert message.
    Always status=BLOCKED. Log at WARNING with full context.
    """


# ---------------------------------------------------------------------------
# 3xx — Orchestrator errors
# The reasoning loop, tool calls, or expert invocations failed.
# Log at ERROR unless it's a known recoverable fault.
# ---------------------------------------------------------------------------

class OrchestratorError(VrakshaError):
    """Base for all orchestrator-layer errors."""


class ToolError(OrchestratorError):
    """
    A tool invocation failed.
    Carry tool name and whether it was a sandbox fault or a tool logic fault.

        raise ToolError("search timed out", tool="search", trace_id=...)
    """
    def __init__(
        self,
        message: str,
        trace_id: str | None = None,
        cause: BaseException | None = None,
        tool: str | None = None,
    ) -> None:
        super().__init__(message, trace_id, cause)
        self.tool = tool

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | tool={self.tool}" if self.tool else base


class ExpertError(OrchestratorError):
    """
    An expert invocation failed.
    Carry expert name and whether it was a routing fault or execution fault.

        raise ExpertError("researcher timed out", expert="researcher", trace_id=...)
    """
    def __init__(
        self,
        message: str,
        trace_id: str | None = None,
        cause: BaseException | None = None,
        expert: str | None = None,
    ) -> None:
        super().__init__(message, trace_id, cause)
        self.expert = expert

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | expert={self.expert}" if self.expert else base


class ToolNotPermittedError(OrchestratorError):
    """
    An expert or the orchestrator tried to invoke a tool it doesn't have
    permission to use. This is a logic error in the system, not a threat.
    """


class ExpertNotPermittedError(OrchestratorError):
    """
    An expert tried to invoke another expert it doesn't have permission
    to contact directly.
    """


class MaxRetriesExceededError(OrchestratorError):
    """
    The orchestrator or output filter retry loop hit its limit.
    Check constants.py: MAX_FILTER_RETRIES, MAX_TOOL_RETRIES.
    """


# ---------------------------------------------------------------------------
# 4xx — Infrastructure errors
# Dependencies, models, memory unavailable or misbehaving.
# These are ops problems, not code problems. Log at ERROR, alert if possible.
# ---------------------------------------------------------------------------

class InfrastructureError(VrakshaError):
    """Base for all infrastructure-layer errors."""


class ModelUnavailableError(InfrastructureError):
    """
    An LLM (orchestrator, verifier, or filter) is unreachable or timed out.
    Triggers circuit breaker if repeated. Carry which model role failed.

        raise ModelUnavailableError("timeout after 5s", model="verifier", trace_id=...)
    """
    def __init__(
        self,
        message: str,
        trace_id: str | None = None,
        cause: BaseException | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(message, trace_id, cause)
        self.model = model

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | model={self.model}" if self.model else base


class MemoryStoreError(InfrastructureError):
    """
    Qdrant or memory manager failed to read, write, or retrieve.
    Non-fatal for read paths if you degrade gracefully.
    Fatal for write paths — data would be lost.

    Named MemoryStoreError (not MemoryError) so it never shadows the Python
    builtin MemoryError — a real out-of-memory condition must stay catchable.
    """


class CircuitOpenError(InfrastructureError):
    """
    A circuit breaker is open — the downstream service is known to be
    unavailable. Fail fast instead of waiting for another timeout.
    Carry which service tripped and when it will retry.

        raise CircuitOpenError("verifier circuit open", service="verifier", retry_after=30.0)
    """
    def __init__(
        self,
        message: str,
        trace_id: str | None = None,
        cause: BaseException | None = None,
        service: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, trace_id, cause)
        self.service = service
        self.retry_after = retry_after

    def __str__(self) -> str:
        base = super().__str__()
        parts = [base]
        if self.service:
            parts.append(f"service={self.service}")
        if self.retry_after is not None:
            parts.append(f"retry_after={self.retry_after}s")
        return " | ".join(parts)


class SandboxError(InfrastructureError):
    """
    The tool execution sandbox failed to start, timed out, or crashed.
    Distinct from ToolError — this is the container/process, not the tool logic.
    """


class ConfigError(InfrastructureError):
    """
    Missing or invalid configuration — env vars, models.yaml, constants.
    Should only ever appear at startup, never mid-request.
    """
