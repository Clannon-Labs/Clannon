# Experts & Tools (Target Roster)

> **Purpose:** The full target roster of experts and tools that widens Clannon
> from a research assistant into a complete workflow platform.
> **Scope:** ~11 experts (domain specialists that reason) and ~16 tools
> (deterministic functions). The expert-vs-tool distinction.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** target roster — not all are built. Confirm built vs. needed against
> the live registry before relying on any single entry.
> **Related:** [README.md](README.md) · [../../glossary/TERMS.md](../../glossary/TERMS.md)

---

Here's the full picture — every expert and tool Vraksha needs to be a complete platform, not just a research assistant.

---

## Experts

Think of experts as **specialized workers** the orchestrator calls when a task needs deep domain knowledge. Each gets a focused system prompt, its own tools, and least-privilege access.

---

**Research Expert**
Finds, reads, and synthesizes information from the web and internal sources. Handles multi-source comparison, recency checks, and source credibility scoring. The most-used expert.

**Documentation Expert**
Writes and structures any kind of document — technical docs, product specs, API docs, changelogs, design docs, decision records, READMEs. Reads existing docs before writing to stay consistent.

**Code Expert**
Reads existing code, writes new code, refactors, debugs, and explains. Follows the repository's conventions. Runs tests. Does not run destructive commands without confirmation.

**Data Analysis Expert**
Works with structured data — CSVs, spreadsheets, SQL results, JSON. Summarizes trends, finds outliers, runs statistical reasoning, and produces charts or tables.

**Media Expert**
Handles images, audio, and video — describes, transcribes, summarizes, extracts information, and flags relevant content. Routes to Gemini by default.

**Citation & Source Verification Expert**
Checks factual claims against their sources. Verifies that citations are accurate, current, and not hallucinated. Used by the output filter path and on-demand.

**Code Execution Expert**
Runs code in a sandboxed environment. Not the same as the Code Expert — this one *executes*, not just writes. Handles test runners, scripts, notebooks, and shell commands safely.

**UI/UX Expert**
Reviews designs, writes UX copy, suggests layout and interaction improvements. Can analyze screenshots. Useful for freelancers doing design work for clients.

**Platform Notification Expert**
Handles delivery to external channels — sends emails, posts to messaging platforms, triggers webhooks. Wraps the delivery layer with intelligence (e.g., knows when to summarize for email vs. give full output on web).

**Memory Curator Expert** *(background, off hot path)*
Runs post-task to review what's worth keeping in memory. Cleans up noise, resolves conflicts between memory tiers, updates confidence scores. Users never see this — it runs silently.

**Summarization Expert**
Condenses long content — transcripts, long documents, research dumps — into digestible formats. Used during session compaction and on-demand.

---

## Tools

Tools are **functions** experts and the orchestrator can call. Unlike experts, tools are deterministic — they don't reason, they just do one thing reliably.

---

**Web Search Tool**
Queries a search engine and returns results with URLs, titles, and snippets. The research expert's primary tool.

**Web Fetch Tool**
Takes a URL and returns the full page content. Used after web search to actually read the article/page.

**Code Runner Tool**
Executes code in a sandboxed environment (Docker or RestrictedPython). Returns stdout, stderr, exit code. Has timeout and output cap enforced.

**File Read Tool**
Reads files from the user's connected storage — R2, local uploads, or linked sources. Used by documentation and code experts.

**File Write Tool**
Writes or updates files — documents, code files, reports. Requires explicit permission check before writing.

**File Patch Tool**
Replaces, inserts, or deletes a precise line range inside a file instead of overwriting the whole thing — the precise-editing primitive for large files (fs.read's whole-file cap silently truncates past ~40k chars; a targeted read+patch reaches past that and avoids clobbering the rest of the file on write). Used by the Code Expert.

**Vector Search Tool**
Queries Qdrant for semantically similar memories. Used by the Memory Manager during hydration. Always scoped to `user_id`.

**Wiki Read Tool**
Reads the user's wiki markdown files from R2. Highest-trust source — used during hydration and when the user references their own knowledge base.

**Wiki Write Tool**
Creates or updates wiki files. Requires the user to have explicitly triggered a save. Never called automatically.

**Database Query Tool**
Runs read queries against Postgres. Used for structured lookups — task history, project metadata, billing state. Never runs writes directly.

**HTTP Request Tool**
Makes outbound API calls to external services (REST APIs, webhooks, integrations). Sandboxed — only allowed domains can be reached.

**Shell Command Tool**
Runs whitelisted shell commands in a restricted environment. Used by the Code Execution Expert. Has an explicit allow-list — no arbitrary commands.

**Screenshot / Browser Tool**
Opens a URL in a headless browser and returns a screenshot or rendered DOM. Used by UI/UX and Media experts for visual analysis.

**PDF Parser Tool**
Extracts structured text and metadata from PDFs. Used during normalization and by the documentation and research experts.

**Chart / Visualization Tool**
Takes structured data and produces a chart (SVG or image). Used by the Data Analysis Expert for reports and deliverables.

**Diff Tool**
Compares two versions of a file or text and returns a structured diff. Used by the Code Expert before making edits.

**Token Counter Tool**
Counts tokens in a payload before an LLM call. Used by the Memory Manager to enforce budget constraints without a live API call.

**MCP Connector Tool** *(post-Macondo)*
Pulls live context from connected external tools — project managers, code hosts, document stores. Data still enters through sanitization.

---

## Quick Summary

| Category | Count | Purpose |
|---|---|---|
| Experts | 11 | Domain specialists that reason and produce output |
| Tools | 16 | Deterministic functions experts call to do things |

