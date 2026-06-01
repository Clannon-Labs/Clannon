# Registry System Guide

The registry system provides a centralized and validated way to register:

* Tools
* Experts (sub-agents)

Registration is performed entirely through decorators.

Users are NOT required to inherit from any base class.

---

# Quick Start

```python
from registry import tool, expert
```

That import is the normal registry API for capability authors. The registry
handles registration internals, so new tools and experts should not need to
import registry entries, adapters, broker internals, or schema constants.

Primitive capability authors may import directly from `registry.register` when
they are intentionally working at the lower-level primitive registration layer.

---

# Basic Tool Registration

Basic tools are normal deterministic helpers. They should provide:

* `name`
* `description`
* `input_schema`
* `call()`

The registry supplies the standard `output_schema`.

```python
from registry import tool


@tool(domain="demo", tags=["basic"])
class ReadMetadata:
    name = "read_metadata"
    description = "Read lightweight metadata for a workspace resource."

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path.",
            }
        },
        "required": ["path"],
    }

    def call(self, tool_input: dict):
        return {
            "success": True,
            "data": {"path": tool_input["path"]},
            "error": None,
        }
```

---

# Primitive Tool Registration

Primitive tools are different. They are the durable execution layer and should
be rare. If a new behavior fits an existing primitive, extend or route through
that primitive instead of creating a new one.

Primitive tools must provide the full explicit contract:

* `name`
* `description`
* `input_schema`
* `output_schema`
* `call()`

Tag primitive tools with `primitive`.

```python
from registry.register import tool


@tool(
    enabled=True,
    domain="filesystem",
    tags=["primitive", "workspace"]
)
class FilesystemOperateTool:
    name = "operate"
    description = "Perform a workspace-scoped filesystem operation."

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            }
        },
        "required": ["query"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "data": {"type": ["object", "null"]},
            "error": {"type": ["string", "null"]},
        },
        "required": ["success"],
    }

    def call(self, tool_input: dict):
        return {"success": True, "data": {}, "error": None}
```

---

# Expert Registration

Minimal expert:

```python
from registry import expert


@expert(domain="review", tags=["code"])
class ReviewExpert:
    name = "review"
    description = "Review proposed changes for correctness, risk, and missing tests."

    input_schema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": "Files, diff, or task scope to review.",
            }
        },
        "required": ["scope"],
    }

    def call(self, tool_input: dict):
        return {
            "success": True,
            "data": {"scope": tool_input["scope"]},
            "error": None,
        }
```

If the expert module sits beside a `SKILL.md`, the registry attaches that file
as `instruction_files` automatically. Explicit `instruction_files` remains
supported for unusual layouts.

```python
@expert(
    domain="finance",
    tags=["analysis", "markets"]
)
class FinanceExpert:
    name = "finance_expert"
    description = "Handles finance-related reasoning"

    input_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Finance question to analyze.",
            }
        },
        "required": ["question"],
    }

    instruction_files = [
        "finance.md"
    ]

    def call(self, tool_input: dict):
        question = tool_input["question"]
        return {"success": True, "data": {"answer": question}, "error": None}
```

---

# Decorator Arguments

## `enabled`

```python
enabled=True
```

Whether the object should be registered.

Default:

```python
True
```

If set to:

```python
enabled=False
```

the class is ignored by the registry.

Useful for:

* testing
* drafts
* experimental tools
* temporary disabling

---

## `domain`

```python
domain="web"
```

Logical namespace/grouping.

Examples:

* `"web"`
* `"filesystem"`
* `"finance"`
* `"database"`

Used internally for canonical registry key generation.

---

## `tags`

```python
tags=["search", "retrieve"]
```

Optional routing metadata.

Tags help:

* orchestrators
* routers
* LLMs
* planners

understand tool/expert capabilities.

---

# Canonical Registry Key

Registry keys are automatically generated.

Format:

```text
{kind}.{domain}.{name}
```

Examples:

```text
tool.web.search_tool
tool.filesystem.read_file
expert.finance.risk_analyzer
```

---

# Validation Rules

All registered objects are validated automatically during registration.

Discovery imports only Python modules that import `registry.register` and use
`@tool` or `@expert`, so decorators must live at module import time.

---

# Required And Defaulted Fields

The registry validates these fields after applying defaults:

```python
name
description
input_schema
output_schema
call()
```

Basic tools and experts define `name`, `description`, `input_schema`, and
`call()`. The registry adds the standard `output_schema` if it is missing.

Primitive tools define every field explicitly, including `output_schema`.

`input_schema` and `output_schema`, whether explicit or defaulted, must be
JSON-schema dictionaries.

`call()` receives one dictionary containing the validated tool arguments and
should return a dictionary, usually:

```python
{"success": True, "data": {...}, "error": None}
```

---

# Required Fields (Experts Only)

Experts MUST additionally have:

```python
instruction_files
```

The preferred layout is a colocated `SKILL.md`:

```text
experts/review/
├── SKILL.md
└── skill.py
```

The registry infers that file automatically. If the expert needs a different
layout, define it explicitly:

```python
instruction_files = [
    "finance.md"
]
```

Rules:

* must be a list
* must contain at least one file
* all files must end in `.md`
* all files must exist

---

# Uniqueness Rules

The following combination MUST be unique:

```text
(kind, domain, name)
```

Meaning:

## INVALID

```python
@tool(domain="web")
class ToolA:
    name = "search"
```

```python
@tool(domain="web")
class ToolB:
    name = "search"
```

Duplicate:

```text
tool.web.search
```

---

## VALID

Tool and expert MAY share the same domain/name pair.

```python
@tool(domain="web")
class SearchTool:
    name = "search"
```

```python
@expert(domain="web")
class SearchExpert:
    name = "search"
```

Generated keys:

```text
tool.web.search
expert.web.search
```

These are distinct.

---

# Internal Metadata

During registration, metadata is attached automatically:

```python
__registry_key__
__registry_kind__
__registry_domain__
__registry_tags__
```

Example:

```python
SearchTool.__registry_key__
# tool.web.search_tool
```

---

# Registry Access

The internal registry stores `RegistryEntry` objects.

Example internal structure:

```python
{
    "tool.web.search_tool": RegistryEntry(...),
    "expert.finance.risk_analyzer": RegistryEntry(...)
}
```

---

# Design Philosophy

The system intentionally uses:

* structural validation
* decorator-based registration
* runtime metadata injection

instead of inheritance-based enforcement.

This keeps plugin authoring:

* simple
* decoupled
* extensible

while preserving strong validation guarantees.

---

# Recommended Conventions

## Naming

Prefer semantic names:

```python
name = "search"
```

instead of:

```python
name = "tool_search"
```

The registry already namespaces automatically.

---

## Domains

Keep domains broad and logical.

Good:

```python
web
filesystem
finance
database
```

Avoid:

```python
web_v2_temp_final
```

---

## Tags

Tags should describe capabilities.

Good:

```python
["search", "retrieve", "internet"]
```

Bad:

```python
["tool", "misc"]
```

---

# Recommended Architecture

## Tools

Use tools for:

* deterministic execution
* APIs
* retrieval
* computation
* filesystem operations
* database operations

Tools should ideally:

* be stateless
* execute quickly
* avoid orchestration logic

---

## Experts

Use experts for:

* reasoning
* planning
* orchestration
* domain-specific cognition
* multi-step workflows

Experts may:

* use tools
* call other experts
* manage context
* perform decomposition
