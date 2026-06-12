# Vraksha: A Friend Who Always Remembers You

<p align="center">
  <img src="https://github.com/vraksha/vraksha/blob/main/assets/vraksha.png" alt="Vraksha Logo" style="width: 30%;">
</p>

> **"Vraksha remembers, so you can focus on creating."**

Most AI assistants start from scratch every time you talk to them. They forget
who you are, what you care about, and what you were building the moment the
session ends. **Vraksha** is being built for the opposite experience: a secure,
local-first agent runtime that can preserve context, understand multimodal
inputs, and grow with you over time.

No more re-explaining. No more context drift. Just get straight to work.

---

## Why Vraksha?

Vraksha is not just another agent wrapper. It is being designed around three
core ideas:

1. **Security that Actually Works**: Powerful agents need strong boundaries.
   Vraksha is built as a layered pipeline where raw input is inspected,
   sanitized, normalized, verified, orchestrated, filtered, and only then shown
   back to the user.
2. **Memory that Lasts**: The long-term vision is a local-first memory system
   that keeps project context, durable facts, and user preferences available
   across sessions without handing everything to a remote black box.
3. **A Personal Agent With Taste**: Vraksha is meant to feel less like a
   disposable chat window and more like a steady collaborator with a consistent
   working style, tool access, and memory.

---

## What it can do right now

- **Flow-Based Pipeline Foundation**: Every stage receives and returns a
  `Flow`, carrying payloads, context, trace metadata, status, and a journal of
  stage transitions.
- **Input Intake Layer**: Vraksha can rate-limit requests, enforce raw input
  size limits, detect modalities, and preserve the original input in request
  context.
- **Security Sanitization Layer**: ClamAV and YARA run concurrently as a
  universal pre-gate before modality workers. Text, PDF, image, audio, and video
  workers validate and sanitize inputs while preserving quality wherever possible.
- **Code-Only Normalization Layer**: Sanitized input is converted into a
  structured `NormalizedInput`. Text and PDFs become clean structured text
  (Unicode-normalized; scanned PDFs route to an OCR expert); image/audio/video
  can stay native when the target model supports them.
- **Verifier Layer**: A small, fast LLM (Google Gemini by default) makes the
  final input-safety call. The deterministic regex pass is only a hint — the LLM
  always adjudicates text and is the sole content blocker. Output is structured.
- **Orchestrator + Experts + Tools**: A Vraksha-owned reasoning loop — the model
  advises with one structured decision per turn and the loop executes it — that
  streams a structured decision log. Experts (web research, writer/synthesis) are
  real agents with their own prompt, skills, and scoped tools; tools (web search,
  fetch URL, sandboxed Python, calculator) run through a permissioned handler.
  Both register through one **capability registry** (`@tool`/`@expert`,
  auto-discovered), so adding a capability is just dropping a decorated file.
- **Output Filter + Delivery**: A final structured safety/groundedness gate checks
  the draft before a delivery stage sends it to the user (CLI today).
- **Memory via a single door**: All memory goes through the `MemoryManager`
  (`MemoryPort`); today a minimal in-process episodic store, with the real
  Qdrant + fastembed tiers as a dedicated next step.
- **Root Model Routing**: Model choices live in `models.yaml`, so every LLM stage
  routes providers from one place; the LLM framework itself is confined to
  `core/llm`. Google Gemini is the default provider.

The active path today is:

```text
raw input -> intake -> sanitizer -> normalizer -> verifier -> orchestrator -> output filter -> delivery
```

---

## Coming Soon

These are the next major layers being built on top of the current foundation:

- **Pydantic AI Orchestrator**: The main reasoning agent that can call tools,
  delegate to experts, and decide what should be remembered.
- **Experts and Tool Handlers**: Controlled execution boundaries for tools,
  specialist models, media understanding, code work, research, and automation.
- **Output Filter**: A final LLM + code safety layer that checks candidate
  responses before the user sees them.
- **Memory Layer**: Persistent local memory for facts, sessions, preferences,
  and project state.

---

## On the Horizon

Here is where Vraksha is heading in the long run:

- **Multimodal Native Reasoning**: Use image/audio/video-capable models when
  available, and route unsupported media to capable experts when needed.
- **Local-First Memory Graph**: A durable memory system combining structured
  records, semantic search, and project-aware context.
- **Agents Talking to Agents**: Multiple Vraksha experts collaborating through
  controlled, auditable boundaries.
- **Sandboxed Execution**: Stronger isolation for tools and code execution
  using Docker today and stricter sandboxes later.
- **Guardian-Style Runtime Checks**: Background integrity checks, health
  monitoring, and safer autonomous behavior.

---

## Architecture Snapshot

```text
foundation/
  Flow, context, constants, shared types, model registry

core/
  intake, pipeline, normalizer, verifier, orchestrator, memory, llm adapter

security/
  sanitizers + output filter

delivery/
  terminal stage (CLI today)

models.yaml
  one place to route model providers and capabilities (Gemini default)

prompts/
  versioned system/instruction prompts as markdown, indexed by registry.yaml
```

Active pipeline:

```text
intake -> sanitizer -> normalizer -> verifier -> orchestrator -> output filter -> delivery
```

Useful docs:

- [foundation/README.md](https://github.com/vraksha/vraksha/blob/main/foundation/README.md)
- [foundation/FLOW_GUIDE.md](https://github.com/vraksha/vraksha/blob/main/foundation/FLOW_GUIDE.md)
- [core/README.md](https://github.com/vraksha/vraksha/blob/main/core/README.md)
- [security/sanitizers/README.md](https://github.com/vraksha/vraksha/blob/main/security/sanitizers/README.md)

---

## Installation

There are two ways to set up Vraksha right now.

### The Fast Path

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

The installer path is meant for the future full runtime. If you are hacking on
the current pipeline layers, the developer path below is the clearest way to
see what is working today.

### The Developer Path

Clone the repo, create a virtual environment, and install dependencies:

```bash
git clone https://github.com/vraksha/vraksha
cd vraksha
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create local env files:

```bash
cp .env.example .env.local
```

Add model keys only for the providers you plan to use. Google Gemini is the
default provider, so `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) is the one you need
unless you change `models.yaml`. Keys go in `.env.local`, which `main.py` loads
at startup; the provider SDK reads the key from the environment.

```env
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
MISTRAL_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
HF_TOKEN=your_hugging_face_key_here
```

Model choices and layer routing live in:

```text
models.yaml
```

### Security Services

ClamAV runs as a daemon. With Docker Compose:

```bash
docker compose up -d clamav
```

Common local settings:

```env
CLAMAV_HOST=127.0.0.1
CLAMAV_PORT=3310
AGENT_YARA_DIR=rules
```

For local media/PDF sanitization, make sure these system packages are present:

```bash
sudo apt-get install -y ffmpeg libimage-exiftool-perl libmagic1
```

On macOS, install equivalent packages with Homebrew:

```bash
brew install ffmpeg exiftool libmagic
```

---

## Verification

Useful checks for the current active layers:

```bash
python -m py_compile \
  foundation/flow.py \
  foundation/constants.py \
  foundation/model_registry.py \
  core/intake/intake.py \
  core/intake/rate_limiter.py \
  security/sanitizers/runner.py \
  security/sanitizers/pre_sanitization.py \
  core/normalizer/normalizer.py
```

```bash
python -m pytest tests/
```

The ClamAV EICAR test requires a running `clamd` daemon. If the daemon is not
available, that test is skipped.

To run the active pipeline end-to-end (intake -> sanitizer -> normalizer ->
verifier) against real ClamAV and a live verifier LLM:

```bash
docker compose up -d clamav          # start the ClamAV daemon
python main.py "your text here"      # prints the resulting Flow summary
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
  
  <p><i>Vraksha: security-first memory agent runtime, built layer by layer.</i></p>
</div>
