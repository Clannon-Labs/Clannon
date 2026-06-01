# Agent Primitive

Purpose: invoke experts through the broker rather than allowing direct
agent-to-expert execution.

Planned capability names:

* `expert_invoke`

Current registry entry:

* `tool.agent.invoke`

Current behavior:

* validates `expert`, `payload`, and `reason`
* fails closed until expert routing policy is implemented

Routing, recursion limits, budgets, and expert allowlists belong at the
broker/policy boundary.
