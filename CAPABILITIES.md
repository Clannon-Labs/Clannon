# Your AI Assistant Capabilities

**Created for:** Abraham Muhammad

This document describes what your AI assistant can do for you — the tools available, what you can accomplish, and how the assistant approaches your requests.

> **How to read this document.** Everything below is marked one of two ways, and
> they are two stages of the same road, not two different lists:
>
> - **✅ Working** — exercised end-to-end and confirmed. If it is marked working,
>   it has actually been run, not just built.
> - **◐ Building** — the machinery exists and is wired in, but it has not been
>   proven end-to-end yet, so it may be uneven. These are the next things to land,
>   not distant ideas.
>
> Nothing here is aspirational marketing. A ◐ is a capability with its foundation
> already in place — the honest distance between "we built it" and "we watched it
> work". Where something is ◐, the note says exactly what is missing.

*Last verified: 2026-08-01.*

---

## Overview

Your AI assistant is a versatile tool designed to help you research, analyze, write, code, and manage projects. Rather than a single monolithic system, the assistant uses **specialized experts** for different domains — you get a documentation expert for writing a README, a data analyst for visualization, a developer for code debugging — all working within a unified interface.

---

## Core Capabilities

### 1. Analysis & Research
- ✅ **Web research** — find current information online with cited sources
- ✅ **Data analysis** — work with datasets, compute statistics, identify trends
- ✅ **Claims verification** — check facts against reliable sources and flag unfounded claims
- ✅ **Content synthesis** — combine information from multiple sources into coherent summaries

### 2. Writing & Documentation
- ✅ **Professional documents** — READMEs, technical specs, design documents, changelogs, decision records
- ✅ **Copy and content** — emails, proposals, marketing copy, reports
- ✅ **Document structure** — organized information that's scannable and actionable
- ✅ **Editing & refinement** — improve clarity, consistency, and tone

### 3. Development & Engineering
- ✅ **Code writing** — new functions, scripts, and programs in multiple languages
- ✅ **Debugging** — understand errors, identify root causes, suggest fixes
- ✅ **Code review** — analyze code quality, security, and best practices
- ✅ **Execution** — run code (where safe and appropriate)

### 4. Project & Task Management
- ◐ **Mission tracking** — break down complex projects into steps and track progress.
  *Durable missions are built and offered to the assistant, but on a long research
  task it currently tends to keep researching rather than opening a mission. Ask for
  it explicitly and expect it to be uneven for now.*
- ◐ **Batch delegation** — queue multiple related tasks and run them systematically
- ◐ **Dependency management** — order tasks correctly when some depend on others
- ✅ **Status reporting** — summarize what's been done and what's next

### 5. Information Extraction
- ✅ **Images** — read text, extract data, identify objects and layout
- ◐ **PDFs** — extract text, tables, and structured information
- ◐ **Audio/Video** — transcribe, summarize, extract key moments.
  *The sanitizers and the media expert handle these; only images have been
  confirmed end-to-end so far.*
- ✅ **Documents** — pull quotes, data, and specific information from long text

### 6. External Delivery
- ✅ **Webhooks & HTTP** — push results to external services and APIs
- ◐ **Slack** — post structured messages and reports via an incoming webhook URL
- ◐ **Discord** — post updates and notifications via a webhook URL
- ◐ **Anything webhook-addressable** — Zapier or a custom endpoint, same mechanism

### 7. Memory Control
- ✅ **Forget learned memory by asking** — when a relevant learned item is visible
  to Clannon, an explicit delete/forget request routes through the authenticated
  Memory Manager and reports success only after storage confirms deletion.
- ✅ **Manual memory control** — user-authored wiki entries and learned entries can
  still be removed from Memory page. Wiki entries remain UI-managed; natural-language
  deletion deliberately cannot guess or delete a wiki entry.

---

## Available Tools

Your assistant has access to the following tools, organized by category:

### Research & Information
| Tool | What It Does |
|------|-------------|
| **Web Search** | Query the internet for current information, with cited sources |
| **Web Fetch** | Retrieve and analyze the full content of web pages |
| **Web Research** | Deep research on a topic, synthesizing multiple sources |

### Data & Analysis
| Tool | What It Does |
|------|-------------|
| **Data Analysis** | Statistical analysis, trend detection, hypothesis testing |
| **Charts & Visualization** | Create graphs, diagrams, and visual representations of data |
| **Calculations** | Perform numerical computations and formula evaluation |

### Writing & Documentation
| Tool | What It Does |
|------|-------------|
| **Document Writing** | Compose technical docs, specs, READMEs, and professional content |
| **Synthesis** | Combine information from multiple sources into coherent narratives |
| **Summaries** | Condense long content into concise overviews |
| **Claims Verification** | Check statements against reliable sources and fact-check |

### Development
| Tool | What It Does |
|------|-------------|
| **Code Engineering** | Write, refactor, and improve code across languages |
| **Code Execution** | Run code safely in controlled environments |
| **Debugging** | Analyze errors, propose fixes, and improve code quality |

### Task Management — ◐ building
| Tool | What It Does |
|------|-------------|
| ◐ **Mission Tracking** | Define objectives, break into steps, track progress toward completion |
| ◐ **Batch Task Delegation** | Queue multiple related tasks and execute systematically |
| ◐ **Dependency Resolution** | Order tasks correctly when one depends on another |

*All three are built and connected — the assistant is offered these tools on every
turn. What is not yet reliable is it reaching for them on its own during a long
task. Say "track this as a mission" to steer it, and tell us when it drifts.*

### Integration & Delivery
| Tool | What It Does |
|------|-------------|
| **Webhooks** | Send structured data to external services via HTTP callbacks |
| **HTTP Requests** | Make API calls to external systems and services |
| **Slack / Discord Delivery** | Post messages, alerts, and reports to a channel you give a webhook URL for |

### Media Analysis
| Tool | What It Does |
|------|-------------|
| ✅ **Image Analysis** | Read text, extract data, identify objects and structure |
| ◐ **PDF Extraction** | Pull text, tables, and metadata from PDF documents |
| ◐ **Audio Transcription** | Convert audio to text, extract key information |
| ◐ **Video Analysis** | Summarize video content, extract text and key moments |

*Uploads are virus-scanned and stripped of metadata before anything reads them, for
every media type. Images are confirmed working end-to-end; the other three share the
same path and are next to be proven.*

### Utilities
| Tool | What It Does |
|------|-------------|
| **Text Diffing** | Compare versions of text and highlight changes |
| **Conversation Recall** | Access documented facts and prior context from previous sessions |
| **File Operations** | Read, write, and organize files in your workspace |

---

## What You Can Do

### Research & Learn
**Ask questions about anything and get cited answers.**

*Example:* "Research the current state of AI regulation in the EU and summarize the key laws."

→ Assistant searches multiple sources, synthesizes findings, cites each claim with sources.

### Analyze Data
**Upload datasets and get insights, charts, and trends.**

*Example:* "Here's Q1 sales data. Show me month-over-month growth and identify which regions are underperforming."

→ Assistant computes metrics, creates charts, flags anomalies, suggests actions.

### Write Professional Documents
**Get well-structured specs, READMEs, changelogs, and proposals.**

*Example:* "Write a README for a Python CLI tool that scrapes web data and exports to CSV."

→ Assistant produces a README with installation, usage examples, API reference, and troubleshooting.

### Debug & Develop Code
**Write, fix, and improve code in any language.**

*Example:* "I'm getting a KeyError in my Flask app when accessing request.form['email']. Debug this."

→ Assistant identifies the issue (missing form field validation), shows the fix, explains why it happened.

### Manage Complex Projects
**Break down large projects into tracked steps.**

*Example:* "I need to redesign my website: audit the current site, sketch new layouts, write responsive HTML/CSS, migrate content."

→ Assistant breaks the work into steps and reports on them. ◐ Durable mission
tracking — subtasks that survive across sessions with done/in-progress/blocked
status — is wired in but not yet reliable on long tasks; say "track this as a
mission" if you want it, and tell us when it doesn't.

### Verify Facts
**Check claims and flag unsupported statements.**

*Example:* "Is it true that 'over 50% of startups fail in their first year'?"

→ Assistant researches, finds actual statistics (nuance: varies by industry/funding), provides sources.

### Summarize Long Content
**Extract the key points from documents, articles, transcripts.**

*Example:* "Here's a 50-page PDF on climate policy. Give me the executive summary."

→ Assistant reads the PDF, identifies main arguments and recommendations, highlights critical data.

### Extract Information from Media
**Pull text and data from images, PDFs, audio, and video.**

*Example:* "This PDF has a table of employee data. Extract it as a CSV."

→ Assistant reads the PDF, finds the table, formats as clean CSV, ready to download.

### Deliver Results Elsewhere
**Send findings, alerts, and documents to Slack, Discord, or external systems.**

*Example:* "Report on website performance and post a summary to my #metrics Slack webhook."

→ Assistant generates the report, formats it for Slack, and posts it. You trigger each
run — there is no built-in scheduler yet, so recurring delivery means asking again or
calling it from your own cron.

---

## How the Assistant Works

### Specialist Experts
Instead of trying to be equally good at everything, your assistant uses **specialized experts for different tasks**:
- A **documentation expert** writes your README or spec
- A **data analyst** creates your charts and statistical summaries
- A **developer** debugs your code
- A **researcher** digs into facts and cites sources

Each expert is trained to handle its domain correctly — better writing, better analysis, better results.

### Breaking Down Complex Tasks
For large projects, the assistant **breaks work into manageable steps**, assigns them to the right experts, and **tracks progress** using mission tracking. You see what's done, what's in progress, and what's blocked.

### Maintaining Context
The assistant **remembers facts you save** (your wiki entries) and recalls relevant context from prior conversations. Your documented facts take priority as the authoritative source of truth.

### Citations & Sources
When researching or verifying claims, the assistant **provides specific sources** — URLs, publication names, dates — so you can verify findings yourself.

### What It Won't Do
- Make up facts, API names, version numbers, or behaviors
- Pretend to know things it doesn't
- Replace human judgment on sensitive decisions
- Access your private accounts, files, or data without explicit permission

When something is unknown or ambiguous, the assistant marks it clearly as `TODO` or `TBD` rather than guessing.

---

## Getting the Most Out of Your Assistant

### 1. Be Specific
Instead of: "Write me a document about my project"  
Try: "Write a 2-page technical spec for a user authentication API with endpoints for sign-up, login, and password reset"

### 2. Provide Context
Share relevant background — prior work, constraints, target audience, examples of what you like. The assistant uses this to produce better results.

### 3. Save Important Facts
Use the wiki feature to record facts you want remembered across all future conversations: your name, your role, your project scope, preferred writing style, etc.

### 4. Break Large Tasks into Missions
Instead of asking for "a complete website redesign," frame it as a mission with specific steps: audit → design → development → testing → deployment.

### 5. Request Citations
When you need research or fact-checking, ask the assistant to cite sources. This makes findings verifiable and trustworthy.

### 6. Iterate
If a document, code, or analysis isn't quite right, tell the assistant what to change. It can refine, restructure, rewrite, or adjust based on your feedback.

---

## Technical Notes

### Your Workspace
The assistant has access to a temporary workspace where it can create, read, and modify files. Documents it writes (like this one) are delivered as downloadable artifacts.

### Memory & Context
- **Wiki (your documented facts)** — Highest priority; saved explicitly by you
- **Conversation history** — Accessible within the current session
- **Prior sessions** — Recalled if you or the assistant saved relevant context

### Performance & Limits
- Most tasks complete in seconds to minutes
- Large data analysis, deep research, and complex development may take longer
- Media processing (images, PDFs, audio) depends on file size and format
- External integrations (Slack, Discord, webhooks) require valid credentials/URLs

---

## Where This Is Going

The ◐ items are not a wishlist. Every one of them already has its machinery built
and wired in — missions are anchored durably in a graph, batches route work to
domain experts, the media sanitizers already scan and clean audio, video and PDF
before anything reads them. The gap is between *built* and *proven*, and closing it
is the current work.

That gap is stated rather than hidden for one reason: a capability list you cannot
trust is worse than a short one. Everything marked ✅ has been run end-to-end. When
a ◐ becomes a ✅, it will be because someone watched it work, not because it was
finished on paper.

The direction, in order:

1. **Prove the rest of media** — PDF, audio and video down the same path images
   already travel.
2. **Make missions reliable** — so a long project holds its shape across sessions
   without being steered back on course.
3. **Deepen what the assistant knows about itself** — richer instructions per
   expert, so it reaches for the right capability without being told.

## Questions?

For specific questions about capabilities, limitations, or how to approach a task,
just ask your assistant. It can walk you through options and help you get started —
and if it does something a ✅ above says it should not, that is a bug worth
reporting.

**Start with any task above, and the assistant will handle the rest.**
