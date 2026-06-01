from __future__ import annotations

from dataclasses import dataclass
from time import monotonic_ns

from registry.discovery import discover_registry_modules
from registry.register import Registry

from .audit import InMemoryAuditLog
from .contracts import CapabilityRequest, CapabilityResult, Usage
from .policy import CapabilityPolicy, FILESYSTEM_CAPABILITIES


@dataclass(slots=True, frozen=True)
class CapabilityRoute:
    """Static mapping from an abstract capability to a registry entry.

    The route lets the agent ask for stable capability names such as
    ``file_read`` without knowing which primitive tool implements the action.
    ``cost_units`` is deliberately simple for now so policy can start enforcing
    budgets before a richer cost model exists.
    """

    capability: str
    registry_key: str
    cost_units: int = 1


DEFAULT_ROUTES: tuple[CapabilityRoute, ...] = (
    CapabilityRoute("expert_invoke", "tool.agent.invoke"),
    CapabilityRoute("file_read", "tool.filesystem.operate"),
    CapabilityRoute("file_write", "tool.filesystem.operate"),
    CapabilityRoute("file_append", "tool.filesystem.operate"),
    CapabilityRoute("file_list", "tool.filesystem.operate"),
    CapabilityRoute("file_search", "tool.filesystem.operate"),
    CapabilityRoute("file_exists", "tool.filesystem.operate"),
    CapabilityRoute("file_stat", "tool.filesystem.operate"),
    CapabilityRoute("llm_generate", "tool.llm.generate"),
    CapabilityRoute("mcp_call", "tool.mcp.call"),
    CapabilityRoute("shell_run", "tool.shell.run"),
    CapabilityRoute("system_inspect", "tool.system.inspect"),
    CapabilityRoute("web_fetch", "tool.web.fetch"),
)


class CapabilityBroker:
    """Policy-enforced router from abstract capabilities to registry entries.

    The broker is the intended safety boundary between the agent/expert layer
    and deterministic tool implementations. It validates the request, checks a
    route, invokes the registered implementation, normalizes the result into a
    ``CapabilityResult``, and records an audit event for every decision.
    """

    def __init__(
        self,
        *,
        policy: CapabilityPolicy | None = None,
        audit_log: InMemoryAuditLog | None = None,
        routes: tuple[CapabilityRoute, ...] = DEFAULT_ROUTES,
        discover: bool = True,
    ) -> None:
        """Create a broker with optional policy, audit, and route overrides.

        ``discover=True`` imports registry modules up front so decorator-based
        tools and experts are available before routing. Tests can disable that
        when they want to inject an already prepared registry.
        """
        if discover:
            discover_registry_modules()

        self.policy = policy or CapabilityPolicy()
        self.audit_log = audit_log or InMemoryAuditLog()
        self.routes = {route.capability: route for route in routes}

    def call(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute one brokered capability request and always audit the result."""
        start_ns = monotonic_ns()
        result = self._call(request, start_ns)
        self.audit_log.record(request, result)
        return result

    def _call(self, request: CapabilityRequest, start_ns: int) -> CapabilityResult:
        """Run the internal request pipeline without duplicating audit writes."""
        route = self._resolve_route(request.capability)
        if route is None:
            return CapabilityResult.fail(
                request,
                "unknown_capability",
                f"unknown capability: {request.capability}",
            )

        denied = self.policy.validate_request(request)
        if denied is not None:
            return denied

        if request.budget_units is not None and request.budget_units < route.cost_units:
            return CapabilityResult.fail(
                request,
                "budget_exhausted",
                f"{request.capability} requires {route.cost_units} budget units",
            )

        entry = Registry.get(route.registry_key)
        if entry is None or not entry.enabled:
            return CapabilityResult.fail(
                request,
                "route_unavailable",
                f"route target is unavailable: {route.registry_key}",
            )

        try:
            output = entry.cls().call(self.policy.prepare_arguments(request))
        except Exception as exc:
            return CapabilityResult.fail(
                request,
                "capability_exception",
                str(exc),
                retryable=False,
            )

        if not isinstance(output, dict):
            return CapabilityResult.fail(
                request,
                "invalid_tool_output",
                f"capability returned invalid type: {type(output)}",
            )

        oversized = self.policy.validate_output(request, output)
        if oversized is not None:
            return oversized

        usage = Usage(
            cost_units=route.cost_units,
            output_bytes=len(str(output).encode("utf-8")),
            elapsed_ms=(monotonic_ns() - start_ns) / 1_000_000,
        )

        if output.get("success") is True:
            data = output.get("data")
            return CapabilityResult.ok(
                request,
                data if isinstance(data, dict) else {"value": data},
                usage=usage,
            )

        return CapabilityResult.fail(
            request,
            "capability_failed",
            str(output.get("error") or "capability failed"),
            usage=usage,
        )

    def supported_capabilities(self) -> list[str]:
        """Return stable routes plus currently registered capability keys."""
        registry_keys = {
            key
            for key, entry in Registry.all().items()
            if entry.enabled
        }
        return sorted(set(self.routes) | registry_keys)

    def _resolve_route(self, capability: str) -> CapabilityRoute | None:
        """Find an explicit route or auto-route a registered capability key.

        Explicit routes keep abstract names such as ``file_read`` available for
        internal orchestration. The fallback route is what makes the broker
        transparent for newly registered tools and experts: once a registry key
        exists, the broker can mediate calls to it without authors adding broker
        code to the capability module.
        """
        route = self.routes.get(capability)
        if route is not None:
            return route

        entry = Registry.get(capability)
        if entry is not None and entry.enabled:
            return CapabilityRoute(capability, capability)

        return None


def filesystem_capabilities() -> dict[str, str]:
    """Expose the stable filesystem capability to primitive operation mapping."""
    return dict(FILESYSTEM_CAPABILITIES)
