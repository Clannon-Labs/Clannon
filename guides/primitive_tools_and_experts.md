# Minimal Capability System Guide

## Overview

This system is built on three layers:

* **Tools** → execute actions
* **Experts** → perform reasoning
* **Capability Broker** → controls access and safety

The agent never executes anything directly. It only requests capabilities.

---

# 1. Primitive Tools

Only a small set of general-purpose tools exist.

## Filesystem Tool

* read, write, list, search files
* restricted to workspace only

## Shell Tool

* executes commands in sandbox
* used for git, python, build tools, etc.

## Web Tool

* search and fetch web content

## LLM Tool

* text generation, summarization, extraction

## Memory Tool

* persistent storage and retrieval

## Agent Tool

* invokes experts via broker

---

# 2. Experts (Reasoning Units)

Experts handle thinking and planning.

## Planner Expert

* breaks tasks into steps
* selects capabilities

## Coding Expert

* writes and modifies code
* uses tools via broker

## Research Expert

* gathers and synthesizes information

## Debugging Expert

* analyzes errors and logs

## Review Expert

* checks correctness and safety

---

# 3. Capability Broker

All execution goes through the broker.

It is responsible for:

* validating requests
* enforcing permissions
* applying policies
* limiting budgets
* routing to tools
* sandbox execution

The agent cannot bypass this layer.

---

# 4. Execution Flow

```text id="flow1"
Agent → Capability Request → Broker → Tool → Sandbox → Result → Agent
```

Example:

1. Agent requests `file_read`
2. Broker checks policy
3. Tool executes inside sandbox
4. Result is returned

---

# 5. Core Rule

> The agent decides what to do.
> The broker decides if it is allowed.
> Tools execute the action.

---

# 6. Design Principle

* Few tools
* Many capabilities
* Strong sandboxing
* Strict policy enforcement

New features should reuse existing tools whenever possible.

Only add new tools when a capability cannot be expressed with current primitives.

---

# 7. Mental Model

* Tools = execution layer
* Experts = reasoning layer
* Broker = safety + control layer
* Agent = decision layer

---

# 8. Minimal Setup

To start:

### Tools

* filesystem
* shell
* web
* llm

### Experts

* planner
* coding
* research

This is sufficient to build a fully functional agent system.
