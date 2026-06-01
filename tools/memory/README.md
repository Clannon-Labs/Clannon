# Memory

Memory is part of the agent orchestrator's cognition, not an external primitive
tool.

The agent-owned gateway lives at:

* `src.agent.memory.AgentMemory`

Use that gateway for essential context and local memory search.

Memory writes are intentionally not exposed as a live capability yet. Add memory
write paths only after policy can adjudicate trust, authority, session
ownership, and poisoning risk.
