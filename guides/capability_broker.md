# Capability Broker Architecture Guide

## Purpose

This document defines the **Capability Broker layer**, which sits between the agent (and experts) and the underlying primitive tools.

The goal is to introduce a **controlled execution boundary** that enforces:

* security
* permissions
* auditing
* rate limiting
* budgeting
* sandbox isolation
* policy enforcement
* observability

while preserving the flexibility of a primitive tool architecture.

Current implementation note: the registry and adapter already expose enabled
tools/experts end-to-end; this broker guide defines the policy boundary to place
between the agent and those implementations.

---

# Core Idea

Instead of the agent calling tools directly:

```text id="b7h2kq"
Agent → Tool
```

The system enforces an intermediate layer:

```text id="k2v8px"
Agent → Capability Request → Broker → Tool Implementation → Sandbox Execution
```

The agent never directly invokes tools.

It only requests **capabilities**.

---

# Why the Broker Exists

Primitive tool architectures fail in production for one reason:

> They assume trust between the agent and execution layer.

This assumption is unsafe.

Without mediation, the following issues emerge:

* unrestricted shell execution
* filesystem escape attempts
* prompt injection → tool misuse
* runaway loops / infinite tool calls
* uncontrolled costs (LLM + web + compute)
* silent exfiltration of secrets
* unlogged destructive actions

The Capability Broker exists to eliminate this trust assumption.

---

# System Overview

## Execution Flow

```text id="r9xw2c"
Agent / Expert
        ↓
Capability Request
        ↓
Capability Broker
        ↓
Policy Engine
        ↓
AuthZ + Budget + Rate Limits
        ↓
Sandbox Router
        ↓
Tool Execution Layer
        ↓
Result
        ↓
Agent
```

---

# Key Abstraction: Capability Request

The agent never calls tools like:

```python id="m3q7aa"
ShellTool.execute(...)
```

Instead, it emits:

```json id="t8c4nq"
{
  "capability": "execute_command",
  "arguments": {
    "command": "git status"
  }
}
```

Or:

```json id="w1k9dp"
{
  "capability": "file_read",
  "arguments": {
    "path": "src/main.py"
  }
}
```

The broker is responsible for routing this request.

---

# Capability Registry

The broker maintains a registry of abstract capabilities:

```text id="c5v7rm"
file_read
file_write
execute_command
web_search
web_fetch
llm_generate
memory_store
memory_retrieve
invoke_expert
```

Each capability maps to:

* one or more implementations
* policies
* sandbox constraints
* cost model

Example:

```text id="h6p0xt"
execute_command
    → ShellTool (docker sandbox)
    → policy: restricted_shell_policy_v3
    → cost: 2 units
```

---

# Policy Layer

Every capability request is validated before execution.

## Policy Structure

```yaml id="p9q2nv"
capability: execute_command

rules:
  allow:
    - git
    - python
    - uv
    - npm
    - node

  deny:
    - sudo
    - rm -rf /
    - chmod 777
    - curl | bash

limits:
  timeout_ms: 10000
  max_output_bytes: 500000
```

---

## Policy Evaluation Order

1. Capability validation
2. Argument sanitization
3. Command inspection (if applicable)
4. Context-based restrictions
5. User/system permissions
6. Budget checks
7. Rate limits

If any stage fails → request is rejected.

---

# Sandbox Layer

All execution occurs in isolated environments.

## Supported sandboxes

```text id="u8j3lx"
Docker containers
Firecracker microVMs
WASM runtimes (lightweight tasks)
Restricted process namespaces
```

## Isolation guarantees

* no host filesystem access
* no system credential access
* no SSH keys
* no privileged syscalls
* network can be disabled or filtered

Even if the agent is compromised, damage remains contained.

---

# Budget System

Every capability has a cost.

Example:

```text id="d7k2mf"
file_read → 1 unit
web_search → 2 units
llm_generate → 5 units
execute_command → 3 units
```

Each session has a budget:

```text id="q1v8nc"
session_budget = 100 units
```

The broker enforces:

* per-request cost
* cumulative cost tracking
* hard stop when budget exhausted

This prevents runaway agent behavior.

---

# Rate Limiting

To prevent abuse and infinite loops:

* per-capability rate limits
* per-session rate limits
* exponential backoff enforcement

Example:

```text id="v5m2xa"
web_search:
  max_requests_per_minute: 10
```

---

# Observability & Logging

Every request is logged:

```json id="s3n6qp"
{
  "timestamp": "...",
  "capability": "execute_command",
  "arguments": "...",
  "policy_result": "allowed",
  "cost": 3,
  "duration_ms": 842,
  "sandbox_id": "vm-221"
}
```

Logs are used for:

* debugging
* security audits
* cost analysis
* behavior tracing
* replay systems

---

# Permission Model

Capabilities can be scoped by:

## 1. User level

* admin
* developer
* restricted
* read-only

## 2. Agent level

* coding agent
* research agent
* autonomous agent
* evaluation agent

## 3. Session level

* ephemeral permissions
* temporary escalations
* approval-based access

---

# Human-in-the-Loop Gate

Certain capabilities require approval:

```text id="f2w7yd"
execute_command (destructive)
memory_delete
filesystem_write outside workspace
network unrestricted access
```

Flow:

```text id="n8p3vq"
Agent requests capability
        ↓
Broker flags as sensitive
        ↓
Human approval prompt
        ↓
Execution allowed / denied
```

---

# Tool Implementation Independence

The broker decouples:

* capability definition
* tool implementation
* runtime provider

Example:

Today:

```text id="l3m8qp"
web_search → SerpAPI
```

Tomorrow:

```text id="z6c1dn"
web_search → local crawler
```

Agent behavior does not change.

---

# Failure Handling

If execution fails:

1. classify error
2. retry if safe
3. fallback implementation if available
4. escalate to agent

Example:

* timeout → retry
* network error → alternate provider
* policy violation → deny immediately

---

# Security Model Summary

The broker enforces:

### 1. No direct tool access

Agent never touches execution layer.

### 2. Policy-first execution

Nothing runs without validation.

### 3. Sandboxed runtime

All execution is isolated.

### 4. Budget constraints

Prevents uncontrolled resource usage.

### 5. Full observability

Every action is traceable.

---

# Design Outcome

With the Capability Broker in place:

* tool surface remains small
* system remains extensible
* new technologies require only new implementations, not new agent logic
* security is centralized instead of scattered
* agent remains flexible but constrained
* system scales to large tool ecosystems without architectural drift

---

# Final Principle

> The agent should be allowed to *request anything*, but never be allowed to *directly execute anything*.

The Capability Broker is the enforcement boundary that makes this possible.
