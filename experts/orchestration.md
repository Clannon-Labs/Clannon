# Expert Orchestration Boundary

Experts do not talk to each other directly.

Every expert-to-expert message must be represented as an `ExpertMessageRequest`
and reviewed by the orchestrator first:

```text
Expert -> ExpertMessageRequest -> Orchestrator -> allow/block -> Expert
```

The orchestrator observes every request, records the decision, and can block
messages that are unnecessary, unauthorized, off-topic, or outside budget.

The current placeholder is intentionally fail-closed. A route must be explicitly
allowed before a message is approved.

Implementation lives in `src.agent`:

* `orchestration/messages.py` defines message requests.
* `orchestration_policy.py` decides allow/block.
* `orchestration/log.py` records observed messages.
* `orchestrator.py` coordinates review and observation.
