# Tests

The tests in this directory cover the current minimal capability surface,
registry discovery, broker policy, agent orchestration boundaries, provider
normalization, and memory behavior.

Registry tests should preserve the process-global `Registry._registry` mapping
around temporary discovery runs. Discovery imports modules for their decorator
side effects, so each test that clears the registry must restore the previous
state before returning.

When adding capability tests, prefer small temporary packages that import only
`tool` or `expert` from `registry.register`. Basic tools should still define
their `name`, `description`, `input_schema`, and `call()` implementation; the
registry supplies the standard output schema. Primitive tools are intentionally
stricter and must define both input and output schemas explicitly.
