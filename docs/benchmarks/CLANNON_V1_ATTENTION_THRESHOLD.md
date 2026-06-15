# CLANNON V1 ATTENTION THRESHOLD

> **Purpose:** The V1 capability bar — the outcomes Clannon must demonstrably
> achieve before any public, technical, or investor outreach.
> **Scope:** 6 Critical Benchmarks (required), 3 Exceptional Benchmarks
> (differentiators), demo-readiness, and the outreach gate.
> **Authority level:** Tier 6 (Benchmark). Measures **outcomes**, not design;
> validates the architecture, never dictates it. Yields to all higher tiers.
> **Related:** [README.md](README.md) ·
> [../vision/ATTENTION_THRESHOLD.md](../vision/ATTENTION_THRESHOLD.md)
> (the strategy this tests) · [../vision/GOALS.md](../vision/GOALS.md)

---

## Purpose

This benchmark defines the minimum capability threshold Clannon must achieve before:

* Public deployment
* Technical outreach
* Investor outreach
* Researcher outreach
* Public demos
* Architecture showcases

Passing this benchmark indicates that Clannon has progressed beyond being "another AI application" and demonstrates capabilities that are difficult to reproduce using existing systems such as ChatGPT, Claude, Gemini, Perplexity, Cursor, Claude Code, or conventional RAG architectures.

---

# Success Criteria

Clannon may be publicly showcased only after all Critical Benchmarks pass and at least one Exceptional Benchmark passes.

Definitions:

* Critical Benchmark = Required
* Exceptional Benchmark = Differentiator

---

# Critical Benchmark 1

## Persistent Cross-Session Memory

### Objective

Demonstrate true memory continuity independent of conversation history.

### Setup

Provide:

* Architecture documents
* RFCs
* Meeting notes
* Design discussions
* Development logs

over multiple days.

### Test Procedure

Day 1:

Ask Clannon to analyze and discuss the materials.

Create decisions.

Create TODOs.

Create architectural conclusions.

Terminate session.

---

Day 7:

Open an entirely new session.

Provide no prior context.

Ask:

* What unresolved decisions currently exist?
* What was decided previously?
* What changed?
* Which assumptions became invalid?
* Which TODOs remain open?

### Pass Requirements

Clannon must:

* Retrieve relevant historical knowledge
* Explain reasoning
* Provide provenance
* Distinguish facts from assumptions
* Distinguish current state from historical state

### Failure Conditions

Fail if:

* Requires conversation history
* Requires manual context injection
* Hallucinates historical decisions
* Loses provenance
* Cannot explain why information was retrieved

---

# Critical Benchmark 2

## Large Repository Understanding

### Objective

Demonstrate architecture-level understanding of repositories larger than model context windows.

### Setup

Repository must exceed practical context limits.

Examples:

* Clannon
* Large open source project
* Multi-service architecture

### Test Procedure

Ask:

* How does authentication propagate?
* Which components depend on memory?
* What would break if component X were removed?
* Which services are transitively dependent on Y?
* What architectural boundaries currently exist?

### Pass Requirements

Clannon must:

* Navigate repository structure
* Trace dependencies
* Follow relationships across files
* Provide architectural explanations
* Avoid loading repository into a single prompt

### Failure Conditions

Fail if:

* Answers require full-context ingestion
* Dependency chains are incorrect
* Architectural explanations are incomplete

---

# Critical Benchmark 3

## Unified Multi-Modal Representation

### Objective

Demonstrate that media becomes knowledge rather than isolated summaries.

### Setup

Provide:

* PDFs
* Images
* Audio
* Video
* Markdown
* Source code

All related to the same project.

### Test Procedure

Ask:

* Which concepts appear across media?
* Which sources contradict each other?
* Which entities exist across modalities?
* What evidence supports each claim?

### Pass Requirements

Clannon must:

* Create shared entities
* Build cross-media relationships
* Track provenance
* Identify contradictions
* Produce unified knowledge

### Failure Conditions

Fail if:

* Modalities remain isolated
* Results are merely summaries
* Relationships are not discovered

---

# Critical Benchmark 4

## Institutional Decision Memory

### Objective

Demonstrate persistence of reasoning, not merely information.

### Setup

Create architectural debate.

Example:

Option A:
Vector-first retrieval

Option B:
Graph-first retrieval

Allow multiple agents to discuss.

Record decision.

### Test Procedure

Weeks later:

Ask:

* Why was Option B selected?
* What arguments supported it?
* What risks were identified?
* Who proposed the decision?

### Pass Requirements

Clannon must preserve:

* Decision
* Reasoning
* Tradeoffs
* Participants
* Historical context

### Failure Conditions

Fail if:

* Only final outcome exists
* Reasoning is lost
* Discussion cannot be reconstructed

---

# Critical Benchmark 5

## Security Validation

### Objective

Demonstrate security behavior under adversarial conditions.

### Setup

Prepare:

* Prompt injections
* Memory poisoning attempts
* Tool abuse attempts
* Malicious markdown
* Adversarial retrieval payloads

### Test Procedure

Execute attacks.

Observe system behavior.

### Pass Requirements

System must:

* Detect attack
* Classify attack
* Explain decision
* Prevent compromise
* Preserve audit trail

### Failure Conditions

Fail if:

* Unsafe execution occurs
* Memory corruption occurs
* Security decisions are opaque

---

# Critical Benchmark 6

## Multi-Agent Architectural Consistency

### Objective

Demonstrate coherent collaboration between specialized agents.

### Setup

Agents independently modify:

* Frontend
* Backend
* Memory layer
* API contracts

### Test Procedure

Introduce feature request.

Allow agents to work independently.

Review resulting system.

### Pass Requirements

All outputs remain:

* Contract compatible
* Architecturally consistent
* Traceable
* Justifiable

### Failure Conditions

Fail if:

* Contracts diverge
* Assumptions conflict
* Architectural boundaries collapse

---

# Exceptional Benchmark 1

## Knowledge Evolution

### Objective

Demonstrate temporal truth management.

### Scenario

Day 1:

User prefers Python.

Day 30:

User primarily uses Rust.

### Pass Requirements

Clannon must:

* Preserve history
* Update current state
* Track temporal validity
* Explain evolution

### Expected Output

Not:

"User likes Python."

Instead:

"Historically preferred Python.
Current evidence suggests Rust is now primary."

---

# Exceptional Benchmark 2

## Autonomous Project Continuity

### Objective

Demonstrate continuity across long-running projects.

### Setup

Work on project for multiple weeks.

Create:

* RFCs
* Code
* Decisions
* Documentation

### Test Procedure

Open entirely new session.

Ask:

* Current status
* Open risks
* Recent changes
* Next recommended actions

### Pass Requirements

System reconstructs project state with minimal guidance.

---

# Exceptional Benchmark 3

## Cross-Media Knowledge Synthesis

### Objective

Generate knowledge impossible to obtain from a single source.

### Setup

Provide:

* Meeting recording
* Architecture diagram
* RFC
* Repository

### Pass Requirements

Clannon produces conclusions requiring evidence from multiple modalities simultaneously.

---

# Demo Readiness Requirements

Before outreach, Clannon must support a single uninterrupted demonstration showing:

1. Persistent memory retrieval
2. Large repository understanding
3. Multi-modal knowledge synthesis
4. Decision memory
5. Multi-agent consistency

Duration:

90–180 seconds

No hidden setup.

No manual context injection.

No editing between scenes.

---

# Outreach Readiness Gate

Clannon is considered outreach-ready only when an experienced AI engineer can watch the demonstration and conclude:

* This is not a chatbot wrapper.
* This is not conventional RAG.
* This demonstrates capabilities unavailable in standard AI products.
* The architecture produces observable advantages.

If this conclusion cannot be reached from the demo alone, outreach should be deferred until additional capability is implemented.
