# Primitive Capability Architecture Guide

## Purpose

This document defines the official architecture for capability exposure within the agent system.

The primary design goal is:

> Give the agent maximum flexibility while maintaining strong security, low maintenance overhead, and long-term scalability.

The system intentionally avoids creating a separate tool for every possible action.

Instead, the agent receives access to a small set of primitive capabilities that can be composed into complex behaviors.

Current implementation note: tools and experts are registered with
`from registry.register import tool, expert`, discovered automatically, and mounted
as callable agent capabilities when `enabled=True`.

---

# Core Philosophy

A common mistake in agent systems is creating a new tool every time a new use case appears.

Example:

```text
ReadFileTool
WriteFileTool
MoveFileTool
CopyFileTool
DeleteFileTool

GitCommitTool
GitPushTool
GitBranchTool

PipInstallTool
NpmInstallTool

DockerBuildTool
DockerRunTool

...
```

This approach appears simple initially but eventually produces:

* hundreds of tools
* duplicate functionality
* difficult maintenance
* inconsistent interfaces
* complicated routing logic

The agent becomes dependent on specific implementations instead of capabilities.

This architecture is intentionally rejected.

---

# The Capability Model

The agent should think in terms of capabilities.

Not implementations.

Bad:

```text
I need ReadFileTool
```

Good:

```text
I need to read a file
```

Bad:

```text
I need GitCommitTool
```

Good:

```text
I need to execute a git command
```

The agent reasons about desired outcomes.

The runtime determines which implementation satisfies the request.

---

# Primitive Capability Strategy

The system provides a small number of powerful primitive tools.

Complex behaviors emerge from combinations of these primitives.

---

# Official Primitive Tools

The following tools form the foundation of the system.

---

## Filesystem Tool

Purpose:

Provide controlled access to workspace files.

Capabilities:

```text
read
write
append
list
search
exists
stat
```

Examples:

```text
Read a file
Write code
Search project files
List directories
Check if file exists
```

The filesystem tool is not responsible for planning.

It only performs filesystem operations.

---

## Shell Tool

Purpose:

Provide controlled command execution.

Capabilities:

```text
execute_command
```

Examples:

```text
python main.py

git status

uv sync

npm install

cargo build
```

The shell tool is intentionally generic.

The system should not create dedicated tools for:

```text
Git
NPM
Cargo
UV
Python
Docker
FFmpeg
```

All of these are command execution tasks.

---

## Web Tool

Purpose:

Provide internet access.

Capabilities:

```text
search
fetch
crawl
```

Examples:

```text
Search documentation
Retrieve web pages
Collect information
Research APIs
```

The web tool should remain provider-agnostic.

The underlying implementation may change without affecting the agent.

---

## Memory Tool

Purpose:

Provide persistent knowledge storage.

Capabilities:

```text
store
retrieve
delete
search
```

Examples:

```text
Store project information
Store user preferences
Retrieve previous findings
```

The memory system is not responsible for reasoning.

Only storage.

---

## LLM Tool

Purpose:

Provide reasoning delegation.

Capabilities:

```text
generate
summarize
classify
extract
```

Examples:

```text
Generate text
Summarize documents
Extract structured data
```

This tool acts as a model interface.

The underlying model may change without affecting the rest of the system.

---

## Agent Tool

Purpose:

Allow expert delegation.

Capabilities:

```text
invoke_expert
```

Examples:

```text
Call Coding Expert
Call Research Expert
Call Finance Expert
```

Experts are treated as capabilities.

Not hardcoded classes.

---

# Why Primitive Tools Scale Better

Consider the following task:

```text
Install FastAPI
Create API
Run tests
Commit changes
Push to GitHub
```

Specialized-tool architecture:

```text
PipInstallTool
CreateApiTool
PytestTool
GitCommitTool
GitPushTool
```

Primitive architecture:

```text
Filesystem Tool
Shell Tool
```

The second solution requires dramatically fewer components.

The capability surface remains stable for years.

---

# Security Architecture

Flexibility without security is unacceptable.

The agent must never have unrestricted access to the host system.

---

# Principle 1

The agent does not control the host.

The agent controls a sandbox.

---

# Principle 2

All dangerous capabilities pass through policy enforcement.

Architecture:

```text
Agent
  ↓
Capability
  ↓
Policy Layer
  ↓
Implementation
```

The agent never reaches implementations directly.

---

# Filesystem Restrictions

The filesystem tool should operate inside:

```text
workspace/
```

or equivalent project root.

Example:

```text
workspace/
├── src/
├── docs/
├── tests/
└── outputs/
```

Blocked locations:

```text
/etc
/root
/home
/usr
~/.ssh
```

The agent must never access arbitrary host files.

---

# Shell Restrictions

Shell execution must pass through a policy engine.

Example policy:

```yaml
allowed:
  - python
  - uv
  - pip
  - git
  - npm
  - node
  - cargo

blocked:
  - sudo
  - chmod
  - chown
  - passwd
  - shutdown
  - reboot
```

Policies may evolve over time.

The agent should never bypass them.

---

# Sandboxing Requirements

Shell execution should run inside:

```text
Docker
Firecracker
MicroVM
Container
```

The preferred design is complete isolation from the host.

Properties:

```text
No root access
No host filesystem
No host secrets
No SSH credentials
No unrestricted networking
```

If the agent behaves incorrectly, only the sandbox is affected.

---

# Capability Evolution

The primitive capability surface should remain small.

New technologies should rarely require new tools.

Example:

Today:

```text
Playwright
```

Tomorrow:

```text
New Browser Framework
```

The browser capability remains:

```text
web_navigation
```

Only the implementation changes.

The agent remains unchanged.

---

# Tool Creation Rules

Before creating a new tool, ask:

Can this already be achieved using existing primitives?

If yes:

Do not create a new tool.

Examples:

```text
Git operations
Package installation
Test execution
Compilation
Formatting
Linting
```

These belong to Shell Tool.

Do not create dedicated wrappers.

---

# Expert Creation Rules

Experts should encapsulate reasoning.

Examples:

```text
Coding Expert
Research Expert
Planning Expert
Review Expert
```

Experts may:

* use tools
* call other experts
* decompose tasks
* coordinate workflows

Experts should not perform low-level execution directly.

Execution belongs to tools.

---

# Long-Term Goal

The ideal system contains:

* very few primitive tools
* many experts
* strong sandboxing
* strict policy enforcement
* capability-based routing

The power of the system should come from composition and reasoning, not from an ever-growing collection of specialized tools.

If a new technology appears tomorrow, the agent should already be able to use it through existing primitive capabilities.

That is the primary objective of this architecture.
