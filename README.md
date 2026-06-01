# Vraksha: A Friend Who Always Remembers You

<p align="center">
  <img src="https://github.com/vraksha/vraksha/blob/main/assets/vraksha.png" alt="Vraksha Logo" style="width: 30%;">
</p>

> **"Vraksha remembers, so you can focus on creating."**

Most AI assistants start from scratch every time you talk to them. They forget who you are and what you're working on the second the session ends. **Vraksha** is different. It’s built with a local-first, persistent memory that actually sticks around. It reads and writes to structured files before and after every session, so your context, project state, and hardcoded rules are never lost.

No more re-explaining. No more context drift. Just get straight to work.

---

## Why Vraksha?

Vraksha isn't just another agent wrapper. We built it on three core ideas that change how it interacts with you and your machine:

1.  **Security that Actually Works**: We believe agents should be powerful without being dangerous. Vraksha uses a multi-gate security architecture (Gate 1 for input sanitization and Gate 2 for action verification) to make sure no command runs without a solid trust score.
2.  **Memory that Lasts**: Your data stays where it belongs: on your machine. Vraksha keeps a relational knowledge graph, a semantic vector store, and a procedural wiki. It doesn't just "chat"; it builds a real understanding of your projects over time.
3.  **Personalities with a Soul**: Every Vraksha instance is unique. You can define a "Soul" for your agent, giving it a distinct voice, its own ethical boundaries, and a specific technical focus.

---

## What it can do right now

-   **Tri-Store Infinite Memory (FTS-Relational Foundation)**: Vraksha utilizes a high-performance local store (SQLite FTS5 + WAL mode) to manage three distinct memory layers. While the dedicated Kùzu graph store is in development, the current foundation supports:
    -   **Wiki (Procedural)**: Durable rules, identities, and project-wide truths.
    -   **Semantic (Episodic)**: Contextual recall of past interactions and decisions.
    -   **Relational Metadata**: Entity tagging and trust-based resolution.
-   **Async I/O Pipeline**: A dedicated `AsyncJournalWriter` factually ensures that logging and memory consolidation never block the agent's reasoning loop.
-   **Modular Skill Registry**: A "drop-in" folder system where new skills/experts (`skill.py` + `SKILL.md`) are automatically discovered and registered at runtime.
-   **Forensic Slop Detection**: A specialized skill (`src/skills/slop_detector`) that differentiates between human-written and AI-generated code.
-   **Security Architecture Baseline**: The technical specifications for the **Multi-Gate Security Stack** are finalized, with the Docker sandbox already serving as the primary execution isolation layer.

---

## Coming Soon (v1.0 Roadmap)

We're actively working on these features and plan to roll them out in the next few weeks:

-   **Multi-Gate Implementation**: Deploying the Gate 1 (Sanitization) and Gate 2 (Intent Verification) logic directly into the agent reasoning loop.
-   **Kùzu Graph Integration**: Moving the relational layer to a dedicated graph database for deep temporal reasoning.
-   **MCP (Model Context Protocol)**: Full support for standardized machine operations (read/write/shell) with automated violation gating.
-   **Composio Integration**: Instant access to 500+ apps like GitHub, Slack, and Notion without any manual setup.
-   **Telegram Interface**: Move your chats from the terminal to a private, secure Telegram bot.

---

## On the Horizon

Here’s where we’re heading in the long run:

-   **Agents Talking to Agents (A2A)**: We want multiple Vraksha instances (like "Luna" for design and "Rex" for dev) to be able to collaborate securely over a local protocol.
-   **Autonomous Heartbeat**: A scheduler that lets Vraksha wake up, do some maintenance, or check on tasks while you're away.
-   **The Guardian Service**: A dedicated service that watches over Vraksha's integrity and keeps it "invisible" when it's not active, making it one of the most secure agents out there.
-   **Sandboxed Execution**: Moving all code execution into gVisor or Firecracker for absolute isolation.

---

## Quick Start

### 1. Get it installed

Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/vraksha/vraksha/main/install-linux.sh | bash
```

WSL:

```bash
curl -fsSL https://raw.githubusercontent.com/vraksha/vraksha/main/install-wsl.sh | bash
```

macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/vraksha/vraksha/main/install-macos.sh | bash
```
> After that, just run `vraksha` to start your first session.

### 2. Set up your keys
Put your API keys in `.env.local`. Vraksha supports all 12 of your favourite providers, including local models.

```bash
ANTHROPIC_API_KEY=your_key_here

OPENAI_API_KEY=your_key_here

GOOGLE_API_KEY=your_key_here

XAI_API_KEY=your_key_here

OPENROUTER_API_KEY=your_key_here

MISTRAL_API_KEY=your_key_here

AWS_BEARER_TOKEN_BEDROCK='your-api-key'
# or:
AWS_ACCESS_KEY_ID='your-access-key'
AWS_SECRET_ACCESS_KEY='your-secret-key'

CEREBRAS_API_KEY='your-api-key'

# Cohere
CO_API_KEY='your-api-key'

GROQ_API_KEY='your-api-key'

OLLAMA_BASE_URL='http://localhost:11434/v1'
OLLAMA_API_KEY='your-api-key'  # required for Ollama Cloud

# To use hugging face models' api
HF_TOKEN=your_hugging_face_key_here #Also for downloading a very small model for memory management (if not already in the repo)

GITHUB_TOKEN=your_key_here #for slop detector expert/skill

# add any other keys your app needs

```

---

## Project Structure

```text
.
├── main.py                # Agent Entry Point
├── memory/                # Where the memory lives (Wiki, Qdrant, Kuzu)
├── src/
│   ├── agent/             # Core LLM logic and prompts
│   ├── memory/            # The memory architecture logic
│   ├── skills/            # Where the skills are stored
│   ├── slop_detector/     # Forensic Code Analysis
│   └── utils/             # GitHub and other utilities
└── assets/                # Logos and documentation images
```

---

**Official Site:** [agentvraksha.com](https://agentvraksha.com)

<div align="center">
  <h3>Vraksha System Architecture & Live Demos</h3>
  
  <table border="0">
    <tr>
      <td>
        <p align="center"><b>01. Introduction/thinking</b></p>
        <img src="https://github.com/vraksha/vraksha/raw/main/assets/previews/introduction.png" width="400" style="border-radius: 6px; border: 1px solid #30363d;">
      </td>
      <td>
        <p align="center"><b>02. Recent Context</b></p>
        <img src="https://github.com/vraksha/vraksha/raw/main/assets/previews/recent.png" width="400" style="border-radius: 6px; border: 1px solid #30363d;">
      </td>
    </tr>
    <tr>
      <td>
        <p align="center"><b>03. Detection Report</b></p>
        <img src="https://github.com/vraksha/vraksha/raw/main/assets/previews/detection-report.png" width="400" style="border-radius: 6px; border: 1px solid #30363d;">
      </td>
      <td>
        <p align="center"><b>04. Detection Feedback</b></p>
        <img src="https://github.com/vraksha/vraksha/raw/main/assets/previews/detector-result-peter.png" width="400" style="border-radius: 6px; border: 1px solid #30363d;">
      </td>
    </tr>
  </table>
  
  <p><i>Vraksha v0.0.10: Previews</i></p>
  <br>
  <p><i>Note: The current version has the local-first memory and security foundations ready to go. We're rolling out the rest of the roadmap features one by one.</i></p>
</div>

