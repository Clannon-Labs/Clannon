# MCP Adapter Placeholder

MCP is a good fit for connecting Vraksha to external tool servers, hosted
systems, IDE integrations, documentation sources, or third-party services.

The project keeps an explicit dependency on the Python `mcp` SDK and imports
its client boundary in `tools/mcp/sdk.py`. The adapter still fails closed until a
real server transport is configured.

Current registry entry:

* `tool.mcp.call`

Current behavior:

* validates external capability call shape
* delegates to the MCP adapter placeholder
* fails closed unless a real MCP server transport is configured

MCP should not be the default path for internal primitive tools or expert
communication. The fast path should stay in-process:

```text
Agent / Expert -> CapabilityRequest -> Broker -> Primitive Tool -> CapabilityResult
```

Use MCP at the edges:

```text
Broker -> MCP Adapter -> External MCP Server -> CapabilityResult
```

This keeps internal routing fast and typed while still leaving a clean place for
portable external integrations.
