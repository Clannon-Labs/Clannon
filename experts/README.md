Legacy experts were moved to `legacy_capabilities_backup/experts/`.

Use this package for the next broker-facing expert implementations.

Experts should communicate through shared capability contracts:

```python
from experts.contracts import CapabilityRequest, CapabilityResult
```

Experts reason, plan, and route. Tools execute. The broker controls permission,
budget, and data movement between them.

Expert-to-expert communication must go through the agent-owned orchestration
boundary in `src.agent.orchestration`. See `experts/orchestration.md`.
