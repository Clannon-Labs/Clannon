from __future__ import annotations

import inspect
from typing import Annotated, Any, Dict, Literal

from pydantic import Field
from pydantic_ai.agent import Agent

from registry.register import Registry
from src.capabilities import Actor, CapabilityBroker, CapabilityRequest


# =========================================================
# TOOL ADAPTER LAYER (MINIMAL + CLEAN)
# =========================================================

class ToolAdapter:
    """
    Converts RegistryEntry objects into PydanticAI-compatible tools.

    Design goal:
        - zero business logic
        - zero string formatting
        - purely structural bridging

    Runtime calls are brokered. The adapter exposes the registered capability
    shape to the LLM, then forwards actual invocations to ``CapabilityBroker``
    using the canonical registry key as the capability name.
    """

    def __init__(self, agent: Agent, broker: CapabilityBroker | None = None):
        """Create an adapter for one agent and one brokered capability surface."""
        self.agent = agent
        self.broker = broker or CapabilityBroker(discover=False)

    # -----------------------------------------------------
    # Core export function
    # -----------------------------------------------------

    def register_all(self) -> None:
        """
        Register all enabled registry entries as PydanticAI tools.

        Registration controls visibility only. The resulting callable still
        goes through the broker, so basic tools, primitive tools, and experts
        share the same policy/audit boundary.
        """

        for key, entry in Registry.all().items():

            # Skip disabled tools
            if not entry.enabled:
                continue

            tool_cls = entry.cls

            self._register_single_tool(entry.key, tool_cls)

    # -----------------------------------------------------
    # Single tool wrapper
    # -----------------------------------------------------

    def _register_single_tool(self, tool_key: str, tool_cls: type) -> None:
        """
        Wrap one registry entry into a PydanticAI-compatible callable.

        ``tool_key`` is preserved as the broker capability name. The LLM sees a
        sanitized version because model tool names cannot contain dots.
        """
        # Pydantic AI / LLM APIs require tool names to match ^[a-zA-Z0-9_-]+$
        safe_name = tool_key.replace(".", "_")

        schema = getattr(tool_cls, "input_schema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        parameters = []
        annotations: dict[str, Any] = {}
        ordered_properties = _required_properties_first(properties, required)
        for prop_name, prop_info in ordered_properties:
            t_str = prop_info.get("type", "any")
            if t_str == "string":
                p_type = str
            elif t_str == "integer":
                p_type = int
            elif t_str == "number":
                p_type = float
            elif t_str == "boolean":
                p_type = bool
            elif t_str == "array":
                p_type = list
            elif t_str == "object":
                p_type = dict
            else:
                p_type = Any
            
            description = prop_info.get("description", "")
            enum_values = prop_info.get("enum")
            if isinstance(enum_values, list) and enum_values:
                p_type = Literal.__getitem__(tuple(enum_values))

            if description:
                annotated_type = Annotated[p_type, Field(description=description)]
            else:
                annotated_type = p_type
            annotations[prop_name] = annotated_type

            if prop_name in required:
                default_val = inspect.Parameter.empty
            else:
                default_val = prop_info.get("default", None)

            param = inspect.Parameter(
                name=prop_name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default_val,
                annotation=annotated_type
            )
            parameters.append(param)

        sig = inspect.Signature(parameters=parameters, return_annotation=Dict[str, Any])

        def wrapped_tool(**kwargs) -> Dict[str, Any]:
            """Forward one model tool call through the broker boundary."""
            request = CapabilityRequest(
                capability=tool_key,
                arguments=kwargs,
                reason=f"LLM invoked registered capability {tool_key}.",
                caller=Actor(kind="agent", name="tool_adapter"),
            )
            return self.broker.call(request).to_tool_output()

        # Apply signature and metadata to the wrapper function
        wrapped_tool.__signature__ = sig
        wrapped_tool.__annotations__ = {**annotations, "return": Dict[str, Any]}
        wrapped_tool.__doc__ = getattr(tool_cls, "description", "")
        wrapped_tool.__name__ = safe_name

        # Register it with the agent
        self.agent.tool_plain(name=safe_name)(wrapped_tool)


def _required_properties_first(
    properties: dict[str, Any],
    required: list[str],
) -> list[tuple[str, Any]]:
    """Return schema properties ordered for a valid Python call signature.

    JSON schema object property order is not a call-signature contract. Python
    requires non-default positional parameters to come before parameters with
    defaults, so the adapter puts required fields first and preserves original
    relative order within the required and optional groups.
    """
    required_names = set(required)
    required_items = [
        (name, info)
        for name, info in properties.items()
        if name in required_names
    ]
    optional_items = [
        (name, info)
        for name, info in properties.items()
        if name not in required_names
    ]
    return required_items + optional_items
