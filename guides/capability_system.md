# Capability System Overview Guide

## Purpose

This document explains how the **Agent Capability System** works end-to-end.

It connects three core components:

* **Tools & Experts Layer** (what exists)
* **Capability Broker Layer** (how access is controlled)
* **Agent Runtime** (how decisions are made)

For deeper details on each component, refer to:

* `tools_and_experts.md`
* `capability_broker.md`

This guide focuses on how they work together in practice.

Current implementation note: enabled `@tool` and `@expert` classes are discovered
and exposed to the agent through the registry adapter today; the broker described
below is the intended enforcement boundary for the next runtime layer.

---

# High-Level Architecture

The system is built around a single idea:

> The agent never executes actions directly. It only requests capabilities.

Execution is always mediated.

```text id="a8xk2p"
Agent → Capability Request → Broker → Tool/Expert → Sandbox → Result → Agent
```

---

# Core Components

## 1. Tools & Experts Layer

This is the execution layer.

### Tools

Tools perform **direct, deterministic actions**, such as:

* reading files
* writing files
* running shell commands
* web requests
* LLM calls

They do not plan or reason.

---

### Experts

Experts are **reasoning and orchestration units**.

They:

* break down tasks
* decide steps
* coordinate tools
* call other experts if needed

They do not directly execute system-level operations without going through tools.

---

## 2. Capability Broker Layer

The broker sits between the agent and execution layer.

It:

* validates requests
* checks permissions
* enforces policies
* applies budgets
* routes to correct tool implementation
* ensures sandbox execution

The agent never bypasses this layer.

---

## 3. Agent Runtime

The agent:

* decides what it wants to do
* emits capability requests
* receives results
* continues reasoning

It does NOT:

* call tools directly
* access system resources
* execute commands

---

# Core Execution Flow

## Step 1 — Agent Decision

The agent identifies a need:

Example:

```text id="k3m8vx"
I need to read a file to understand the project structure.
```

---

## Step 2 — Capability Request

The agent converts intent into a structured request:

```json id="q7n2wd"
{
  "capability": "file_read",
  "arguments": {
    "path": "src/main.py"
  }
}
```

---

## Step 3 — Broker Validation

The Capability Broker:

* checks if `file_read` is allowed
* validates the file path (workspace only)
* checks budget
* checks rate limits
* applies security policies

If any rule fails → request is rejected.

---

## Step 4 — Tool Execution

If allowed:

* broker selects correct tool implementation
* tool executes inside sandbox
* output is captured

Example:

```text id="v9p4ms"
FilesystemTool.read("src/main.py")
```

---

## Step 5 — Return Result

The result flows back:

```json id="t1x6rk"
{
  "capability": "file_read",
  "result": "file contents..."
}
```

Agent receives it and continues reasoning.

---

# Capability Flow Model

Every action in the system follows this structure:

```text id="c6y9ab"
Intent → Capability → Policy Check → Execution → Result
```

---

# Why This Separation Exists

The system is intentionally split into layers to achieve:

## 1. Safety

Agent cannot directly execute system commands.

All actions are filtered through policy enforcement.

---

## 2. Stability

Tool implementations can change without affecting agent behavior.

Example:

* today: `web_search → SerpAPI`
* tomorrow: `web_search → local crawler`

Agent sees no difference.

---

## 3. Scalability

Instead of adding new tools constantly:

* reuse primitives
* expand capabilities only when needed
* keep system stable as it grows

---

## 4. Composability

Complex behavior emerges from:

* tool primitives
* expert reasoning
* capability orchestration

Not from one-off tools.

---

# Relationship Between Components

## Tools vs Experts

| Component | Role      |
| --------- | --------- |
| Tools     | Execution |
| Experts   | Reasoning |

---

## Broker vs Tools

| Component | Role                 |
| --------- | -------------------- |
| Broker    | Control & validation |
| Tools     | Do the actual work   |

---

## Agent vs Broker

| Component | Role                  |
| --------- | --------------------- |
| Agent     | Requests capabilities |
| Broker    | Decides if allowed    |

---

# Example Workflow (End-to-End)

Task:

> “Analyze a Python project and run tests”

---

### 1. Agent plans

```text id="p3v7nm"
Need to:
- read project files
- run test suite
```

---

### 2. Capability requests

```json id="r5k1cq"
{ "capability": "file_read", "args": { "path": "src/" } }
```

```json id="w8m2xf"
{ "capability": "execute_command", "args": { "command": "pytest" } }
```

---

### 3. Broker checks

* file_read → allowed
* execute_command → allowed inside sandbox

---

### 4. Execution

* filesystem tool reads files
* shell tool runs pytest in container

---

### 5. Results returned

Agent receives:

* file contents
* test output

---

### 6. Agent continues reasoning

Agent updates understanding and proceeds.

---

# Key Design Rule

> The agent is powerful in reasoning, but restricted in execution.

> The broker is strict in execution, but blind in reasoning.

This separation is what makes the system both flexible and safe.

---

# Mental Model for Developers

When working with this system, think in three layers:

```text id="x7c2dp"
1. What the agent wants (Intent)
2. What capability is required (Capability)
3. Whether it is allowed and how it executes (Broker + Tools)
```

---

# Extending the System

To add new functionality:

## Do NOT:

* create a new agent behavior

## DO:

1. define a new capability (if necessary)
2. map it to existing tools OR implement new tool
3. register it in broker policy system

Agent logic stays unchanged.

---

# Summary

* Tools = execution primitives
* Experts = reasoning modules
* Broker = security + control layer
* Agent = decision maker

The system is designed so that:

> Increasing capability does not require increasing agent complexity.

Only the execution layer evolves; the agent remains stable.
