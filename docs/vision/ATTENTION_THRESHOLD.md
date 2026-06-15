# Attention Threshold (Architecture Addendum)

> **Purpose:** The strategic lens that defines what Clannon must *prove* before
> it earns attention, and the priorities that follow from it.
> **Scope:** The four demonstration pillars, memory promotion/typing policy, the
> demonstration-first rule, and the outreach gate.
> **Authority level:** Tier 2 (Vision). **Supersedes architecture decisions when
> engineering elegance and demonstrability conflict.** It does *not* supersede
> the Invariants (Tier 1) — safety, transport, identity, and trust rules hold
> even for a demo.
> **Related:** [00_START_HERE.md](../00_START_HERE.md) ·
> [INVARIANTS.md](INVARIANTS.md) · [GOALS.md](GOALS.md) ·
> [../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
> (the benchmark that tests this)

---

# CLANNON_ATTENTION_THRESHOLD_ARCHITECTURE_ADDENDUM

## Purpose

This document supersedes all architecture decisions whenever there is a conflict between:

* Engineering cleanliness
* Demonstrability

Clannon's first objective is not production readiness.

Clannon's first objective is proving a capability that causes experienced AI engineers, researchers, and investors to immediately recognize that Clannon is fundamentally different from conventional chat systems, RAG systems, and agent wrappers.

---

# Core Principle

The system shall optimize for:

> Capability visibility over architectural elegance.

A capability that is invisible to users does not exist.

A capability that cannot be demonstrated in under three minutes does not contribute to Clannon's moat.

---

# The Four Demonstration Pillars

Every architectural decision should strengthen at least one pillar.

> **Each pillar has exactly one architecture home** (so coverage is verifiable):
> see the **pillar → architecture home** table in
> [../00_START_HERE.md](../00_START_HERE.md). Homes marked *proposed* document a
> target, not a shipped capability — confirm state in
> [../architecture/INVARIANT_OWNERSHIP.md](../architecture/INVARIANT_OWNERSHIP.md).

---

## Pillar 1

### Persistent Organizational Memory

Clannon must remember:

* Decisions
* Tradeoffs
* Failed approaches
* Open questions
* Assumptions
* Architectural reasoning

Memory is not conversation storage.

Memory is organizational continuity.

---

### Required Capability

A new session must answer:

* Why was a decision made?
* What alternatives existed?
* What risks were accepted?
* What assumptions led to the decision?

without access to prior conversation history.

---

### Architecture Requirement

Every significant decision must generate:

```text
Decision
Reasoning
Alternatives
Risks
Evidence
Timestamp
Participants
```

stored as a first-class memory artifact.

---

### Retrieval Requirement

Decision retrieval must outrank ordinary conversation retrieval.

Institutional memory is higher value than chat history.

---

# Pillar 2

### Cross-Media Knowledge Graph

Clannon shall not treat modalities as independent artifacts.

Everything becomes knowledge.

---

### Forbidden Design

```text
PDF summary

Image summary

Audio summary

Video summary
```

stored separately.

---

### Required Design

All modalities produce:

```text
Entities
Relationships
Claims
Events
Sources
Evidence
```

inside a shared representation.

---

### Example

A PDF mentioning:

```text
Memory Manager
```

An architecture diagram showing:

```text
Memory Manager
```

A meeting recording discussing:

```text
Memory Manager
```

must converge into a single entity.

---

### Success Condition

The system can answer questions requiring multiple modalities simultaneously.

---

# Pillar 3

### Repository Intelligence

Clannon must understand systems larger than context windows.

---

### Required Capability

Questions such as:

```text
What would break if component X disappeared?

Which services depend on Y?

Why was architecture Z chosen?
```

must be answerable without loading the entire repository.

---

### Architecture Requirement

Repository ingestion produces:

```text
File Graph

Dependency Graph

Architectural Graph

Decision Graph

Ownership Graph
```

---

### Forbidden Behavior

Repository reasoning must never rely on:

```text
Massive prompt stuffing
```

---

# Pillar 4

### Agent Civilization

Multiple agents must appear as one coherent organization.

---

### Required Capability

Weeks later:

The system must explain:

```text
Who made a decision

Why they made it

Who objected

What changed
```

---

### Architecture Requirement

All agents communicate through artifacts.

Never through hidden context.

---

### Required Artifact Types

```text
RFC

Decision

Objection

Investigation

Contract

Migration

Risk
```

---

# Memory Promotion Policy

The current memory architecture is expanded.

---

## Promotion Priority

Highest:

```text
Decision
```

Then:

```text
Contract
```

Then:

```text
Risk
```

Then:

```text
Finding
```

Then:

```text
Conversation
```

Conversation should be the least important memory type.

---

# Knowledge Representation

Memory entries must be typed.

---

## Required Types

```text
Fact

Claim

Assumption

Decision

Risk

Preference

Procedure

Event

Contract

Entity

Relationship
```

---

## Forbidden Type

```text
Unstructured blob
```

---

# Demonstration First Rule

Before implementing any major subsystem:

Ask:

```text
Can this capability be demonstrated?
```

If not:

Do not prioritize implementation.

---

# Outreach Readiness Gate

Clannon is outreach-ready only when all conditions are true.

---

## Condition 1

A completely new session can reconstruct:

* Project state
* Architectural decisions
* Open risks
* Historical reasoning

without chat history.

---

## Condition 2

A user can upload:

* PDF
* Image
* Video
* Audio
* Source code

and receive a unified knowledge representation.

---

## Condition 3

A repository larger than context limits can be explored and reasoned about.

---

## Condition 4

Agent decisions survive sessions and remain explainable.

---

## Condition 5

The entire capability can be demonstrated in under three minutes.

---

# Founder Responsibility

The founder must retain ownership of:

* Architecture
* Invariants
* Contracts
* Failure Modes
* Memory Policy
* Security Policy

The founder is not required to know:

* Individual implementations
* Framework internals
* UI details
* Provider SDK details

No critical architectural decision may exist solely in code.

Every important decision must exist in architecture artifacts.

---

# Final Rule

Clannon should not attempt to beat ChatGPT at chatting.

Clannon should not attempt to beat Claude at coding.

Clannon should not attempt to beat Perplexity at search.

Clannon should become the system that remembers, understands, and evolves projects over time better than any of them.

Every subsystem should be evaluated against that objective.
