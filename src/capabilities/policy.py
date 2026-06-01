from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from resolve.resolve_within_project import PROJECT_ROOT, resolve_path
from src.utils.immutables import is_immutable

from .contracts import CapabilityRequest, CapabilityResult


FILESYSTEM_CAPABILITIES = {
    "file_read": "read",
    "file_write": "write",
    "file_append": "append",
    "file_list": "list",
    "file_search": "search",
    "file_exists": "exists",
    "file_stat": "stat",
}

POLICY_DISABLED_CAPABILITIES = {
    "expert_invoke",
    "llm_generate",
    "mcp_call",
    "shell_run",
    "web_fetch",
}

POLICY_DISABLED_REGISTRY_PREFIXES = (
    "tool.agent.",
    "tool.llm.",
    "tool.mcp.",
    "tool.shell.",
    "tool.web.",
)


@dataclass(slots=True, frozen=True)
class PolicyLimits:
    """Tunable caps applied before and after capability execution.

    These values are intentionally conservative. They make the first broker
    useful for filesystem work while preventing accidental giant reasons,
    oversized paths, broad directory listings, and unbounded tool output.
    """

    max_reason_chars: int = 500
    max_path_chars: int = 500
    max_output_bytes: int = 250_000
    max_read_bytes: int = 60_000
    max_search_results: int = 50
    max_list_depth: int = 3


class CapabilityPolicy:
    """Fail-closed policy checks for brokered capability requests.

    The policy layer owns validation and argument shaping. The broker decides
    where a capability goes; this class decides whether the request is safe
    enough to execute and clamps caller-provided limits before the primitive
    tool sees them.
    """

    def __init__(self, limits: PolicyLimits | None = None) -> None:
        """Create a policy with default or caller-supplied execution limits."""
        self.limits = limits or PolicyLimits()

    def validate_request(self, request: CapabilityRequest) -> CapabilityResult | None:
        """Return a failure result when a request violates policy.

        ``None`` means the request is allowed to proceed to routing/execution.
        Returning a full ``CapabilityResult`` keeps broker errors structured and
        avoids exception-driven control flow for expected denials.
        """
        if not request.reason.strip():
            return CapabilityResult.fail(
                request,
                "reason_required",
                "capability requests must include a reason",
            )

        if len(request.reason) > self.limits.max_reason_chars:
            return CapabilityResult.fail(
                request,
                "reason_too_large",
                f"reason must be at most {self.limits.max_reason_chars} characters",
            )

        if request.budget_units is not None and request.budget_units < 1:
            return CapabilityResult.fail(
                request,
                "budget_exhausted",
                "request budget must be at least 1 unit",
            )

        if request.capability in FILESYSTEM_CAPABILITIES:
            return self._validate_filesystem_request(request)

        if (
            request.capability in POLICY_DISABLED_CAPABILITIES
            or request.capability.startswith(POLICY_DISABLED_REGISTRY_PREFIXES)
            or request.capability.startswith(("shell_", "web_", "network_"))
        ):
            return CapabilityResult.fail(
                request,
                "capability_not_enabled",
                f"{request.capability} is not enabled by policy",
            )

        return None

    def validate_output(
        self,
        request: CapabilityRequest,
        output: dict[str, Any],
    ) -> CapabilityResult | None:
        """Reject outputs that cannot be serialized or exceed the byte cap."""
        try:
            encoded = json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")
        except (TypeError, ValueError):
            return CapabilityResult.fail(
                request,
                "invalid_tool_output",
                "tool output must be JSON serializable",
            )

        if len(encoded) > self.limits.max_output_bytes:
            return CapabilityResult.fail(
                request,
                "output_too_large",
                f"tool output exceeded {self.limits.max_output_bytes} bytes",
            )

        return None

    def prepare_arguments(self, request: CapabilityRequest) -> dict[str, Any]:
        """Translate abstract capability arguments into primitive tool input.

        Filesystem capabilities share ``tool.filesystem.operate`` internally,
        so this method injects the primitive ``operation`` and clamps any
        caller-supplied limits to policy-approved maximums.
        """
        if request.capability not in FILESYSTEM_CAPABILITIES:
            return dict(request.arguments)

        prepared = dict(request.arguments)
        prepared["operation"] = FILESYSTEM_CAPABILITIES[request.capability]

        if "max_bytes" in prepared:
            prepared["max_bytes"] = self._clamp_positive_int(
                prepared["max_bytes"],
                self.limits.max_read_bytes,
            )
        if "max_results" in prepared:
            prepared["max_results"] = self._clamp_positive_int(
                prepared["max_results"],
                self.limits.max_search_results,
            )
        if "max_depth" in prepared:
            prepared["max_depth"] = self._clamp_positive_int(
                prepared["max_depth"],
                self.limits.max_list_depth,
            )

        return prepared

    def _validate_filesystem_request(
        self,
        request: CapabilityRequest,
    ) -> CapabilityResult | None:
        """Apply workspace path, immutable-file, and query checks."""
        path_value = str(request.arguments.get("path", "")).strip()
        if not path_value:
            return CapabilityResult.fail(request, "path_required", "path is required")

        if len(path_value) > self.limits.max_path_chars:
            return CapabilityResult.fail(
                request,
                "path_too_large",
                f"path must be at most {self.limits.max_path_chars} characters",
            )

        resolved = resolve_path(path_value)
        if not resolved.success or resolved.result is None:
            return CapabilityResult.fail(
                request,
                "path_outside_project",
                resolved.error or "path is outside project root",
            )

        target = resolved.result
        if _contains_hidden_dependency_part(target):
            return CapabilityResult.fail(
                request,
                "path_blocked",
                "dependency, cache, and VCS paths are not broker-readable",
            )

        operation = FILESYSTEM_CAPABILITIES[request.capability]
        if operation in {"write", "append"} and is_immutable(target):
            return CapabilityResult.fail(
                request,
                "immutable_path",
                f"{_relative(target)} is immutable",
            )

        if operation == "search" and not str(request.arguments.get("query", "")).strip():
            return CapabilityResult.fail(
                request,
                "query_required",
                "query is required for file_search",
            )

        return None

    def _clamp_positive_int(self, value: Any, maximum: int) -> int:
        """Parse a positive integer and cap it at the configured maximum."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return maximum
        return min(max(parsed, 1), maximum)


def _contains_hidden_dependency_part(path: Path) -> bool:
    """Return true for workspace paths inside noisy or sensitive folders."""
    blocked_parts = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
    }
    try:
        parts = path.resolve().relative_to(PROJECT_ROOT).parts
    except ValueError:
        return True
    return any(part in blocked_parts for part in parts)


def _relative(path: Path) -> str:
    """Format a path relative to the project root when possible."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
