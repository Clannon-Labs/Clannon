# Capabilities

This package contains the request/result contracts and the first brokered
execution boundary for Vraksha capabilities.

## Current Shape

`CapabilityRequest` and `CapabilityResult` are the stable envelopes shared by
the agent, broker, tools, and experts. The broker currently routes a small set
of stable capability names to the live primitive registry entries:

- `expert_invoke`
- `file_read`
- `file_write`
- `file_append`
- `file_list`
- `file_search`
- `file_exists`
- `file_stat`
- `llm_generate`
- `mcp_call`
- `shell_run`
- `system_inspect`
- `web_fetch`

The filesystem capabilities all route through `tool.filesystem.operate`; the
agent-facing capability name stays abstract while the broker injects the
primitive operation.

The not-yet-safe edge primitives (`expert_invoke`, `llm_generate`, `mcp_call`,
`shell_run`, and `web_fetch`) are routed but policy-disabled until their
budgets, sandboxes, providers, transports, or network controls are designed.

## Policy Boundary

`CapabilityPolicy` is fail-closed. It requires a request reason, enforces
workspace path resolution, blocks immutable writes, rejects empty search
queries, caps caller-provided filesystem limits, and rejects oversized outputs.

Shell, web, external MCP, LLM, and expert-invocation capabilities are not
enabled here yet. They should only be opened with explicit policy rules, tests,
and sandbox or provider decisions.

## Audit Boundary

`InMemoryAuditLog` records every broker decision. It is intentionally small for
now, but the `AuditEvent` shape is suitable for replacing the sink with a
durable append-only log later.
