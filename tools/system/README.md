# System Primitive

Purpose: expose safe, read-only project/runtime metadata to the agent.

Legacy system tools were moved to `legacy_capabilities_backup/tools/`.

Current registry entry:

* `tool.system.inspect`

Supported behavior:

* returns project root metadata
* returns bounded Python runtime metadata
* avoids environment variables, secrets, user home inspection, and arbitrary
  host state
