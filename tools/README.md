# Tools

Primitive tools execute deterministic work for the capability broker.

Use `tools.contracts` for broker-facing request/result data:

```python
from tools.contracts import CapabilityRequest, CapabilityResult
```

Keep tool implementations small and side-effect explicit. Validation, budgets,
permissions, and routing belong at the broker/policy boundary.
