# Agent Tool Initialization

This package turns registry entries into model-visible PydanticAI tools.

`ToolAdapter` is intentionally a bridge, not the execution owner. It exposes
the registry entry's name, description, and input schema to the model, but every
runtime invocation is forwarded through `CapabilityBroker` using the canonical
registry key.

That means capability authors do not have to import or call the broker. Once a
tool or expert is registered and mounted, the adapter gives it the broker's
policy, result normalization, and audit boundary automatically.

## Output Contract

Always return structured JSON-like dictionaries from tools, experts, and broker
wrappers. Never return a bare string.

## Use the data types shown below

```json
        "success": {"type": "boolean"},
        "data": {"type": ["object", "null"]},
        "error": {"type": ["string", "null"]}
```

```json
    "success": {"type": "boolean"},
    "data": {
        "type": "object",
        "properties": {
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "exit_code": {"type": "integer"}
        }
    },
    "error": {"type": ["string", "null"]}
```
