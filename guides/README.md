# Capability Authoring Guide

## Purpose

This guide explains how to add, edit, disable, and test any tool or expert in
Vraksha.

Use this as the practical contributor guide. The architecture guides explain
why the system exists; this file explains what to do when changing it.

Related references:

* `guides/capability_system.md`
* `guides/tools_and_experts.md`
* `guides/capability_broker.md`
* `registry/README.md`

---

# Current Runtime Model

Today, enabled tools and experts are exposed through this flow:

```text
Python module import
    ↓
@tool / @expert decorator runs
    ↓
Registry stores entry
    ↓
Discovery finds registry modules
    ↓
ToolAdapter mounts entries on the agent
    ↓
LLM sees tool name, description, and input schema
```

The future broker layer will sit between the agent and implementation. Until
then, every tool and expert must be written as if it is crossing a security
boundary.

---

# Golden Rules

1. Use `@tool` for deterministic execution.
2. Use `@expert` for reasoning, analysis, planning, or orchestration.
3. Do not create narrow wrapper tools for commands that the shell primitive can
   handle.
4. Keep tool schemas simple and explicit.
5. Return structured dictionaries, not plain strings.
6. Use `enabled=False` for drafts or temporarily disabled capabilities.
7. Never perform dangerous host actions outside the existing safety helpers.

---

# How Discovery Works

A module is discovered only if it:

* imports decorators from `registry` or `registry.register`
* contains `@tool` or `@expert`
* is not under ignored folders such as `tests/`, `.venv/`, `venv/`, `.git/`,
  caches, assets, or memory

This means a capability can live anywhere importable in the project, but the
decorated class must exist at module import time.

Good:

```python
from registry import tool

@tool(enabled=True, domain="filesystem", tags=["read"])
class ReadFile:
    ...
```

Bad:

```python
def register_later():
    @tool(domain="filesystem")
    class ReadFile:
        ...
```

---

# Adding a Tool

Use a tool when the behavior is direct and deterministic.

Example:

```python
from __future__ import annotations

from typing import Any, Dict

from registry import tool


@tool(enabled=True, domain="filesystem", tags=["read"])
class ReadSomethingTool:
    name = "read_something"
    description = "Read a project-scoped resource and return structured data."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the project root.",
            }
        },
        "required": ["path"],
    }
    def call(self, tool_input: dict) -> Dict[str, Any]:
        path = str(tool_input.get("path", "")).strip()
        if not path:
            return {"success": False, "data": None, "error": "path is required"}

        return {
            "success": True,
            "data": {"path": path},
            "error": None,
        }
```

Tool requirements:

* `name`: stable semantic name
* `description`: clear instruction for when to use the tool
* `input_schema`: JSON-schema dictionary
* `output_schema`: optional for basic tools; required for primitive tools
* `call(self, tool_input: dict)`: returns a dictionary

The LLM sees the registry key converted to a safe name:

```text
tool.filesystem.read_something → tool_filesystem_read_something
```

---

# Adding an Expert

Use an expert when the behavior requires reasoning, domain analysis, or
multi-step orchestration.

Example:

```python
from __future__ import annotations

from typing import Any, Dict

from registry import expert


@expert(enabled=True, domain="review", tags=["code", "analysis"])
class CodeReviewExpert:
    name = "code_review"
    description = "Analyze code changes for bugs, regressions, and missing tests."
    input_schema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": "Files, directories, or change description to review.",
            }
        },
        "required": ["scope"],
    }
    instruction_files = ["experts/code_review/SKILL.md"]

    def call(self, tool_input: dict) -> Dict[str, Any]:
        scope = str(tool_input.get("scope", "")).strip()
        if not scope:
            return {"success": False, "data": None, "error": "scope is required"}

        return {
            "success": True,
            "data": {
                "scope": scope,
                "instructions": self.instruction_files,
            },
            "error": None,
        }
```

Expert requirements are the same as tools, plus:

* `instruction_files`: non-empty list of existing `.md` files

Experts should not directly perform low-level execution. They should reason,
route, plan, or delegate to tools.

The LLM sees:

```text
expert.review.code_review → expert_review_code_review
```

---

# Disabling a Capability

Use `enabled=False`:

```python
@tool(enabled=False, domain="web", tags=["draft"])
class DraftWebTool:
    ...
```

Disabled classes are ignored by the registry and will not be mounted on the
agent.

Use this for:

* incomplete tools
* experiments
* unsafe capabilities
* temporary rollback

---

# Editing an Existing Tool or Expert

When editing, check these things:

1. Does the `description` clearly tell the LLM when to use it?
2. Does the schema include every required argument?
3. Are optional arguments given safe defaults?
4. Does the tool return `{"success", "data", "error"}`?
5. Does the implementation respect project-root and immutable-file rules?
6. Does the capability belong as a primitive tool, or should it be an expert?
7. Does `llm_view_snapshot.json` show the intended name and schema?

Do not change `name`, `domain`, or argument names casually. The LLM and tests use
those as the public interface.

---

# Testing What the LLM Sees

Run:

```bash
.venv/bin/python -m pytest tests/test_llm_view.py -q
```

Then inspect:

```text
llm_view_snapshot.json
```

Check:

* tool/expert name
* description
* required fields
* defaults
* enums
* output settings

Run the whole suite before finishing:

```bash
.venv/bin/python -m pytest
```

---

# When Not to Add a New Tool

Do not add a tool if an existing primitive can do the job.

Examples that should usually use shell:

* git commands
* package installs
* test execution
* linting
* formatting
* compilation

Examples that should usually use filesystem:

* read
* write
* append
* list
* delete
* exists
* stat

Add a new tool only when there is a genuinely new primitive capability or a
security boundary that deserves its own policy.

---

# Security Checklist

Before enabling a capability:

* Is it scoped to the project root?
* Does it reject unsafe or missing arguments?
* Does it avoid leaking secrets?
* Does it avoid unbounded output?
* Does it avoid unbounded network or filesystem traversal?
* Does it use existing sandbox or resolver helpers where applicable?
* Would it still be safe if a prompt-injected model called it repeatedly?

If any answer is unclear, keep it disabled.

---

# Summary

Use decorators to declare capabilities, keep schemas explicit, keep tools
primitive, keep experts reasoning-focused, and verify the final agent-facing
surface through `tests/test_llm_view.py`.
