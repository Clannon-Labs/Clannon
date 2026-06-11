# Vraksha

Vraksha is a research pipeline with memory. You give it a brief, it plans
the work, sends out agents that can actually search the web and run code,
checks the answer before showing it to you, and saves what it learned so
the next run starts smarter. I built it because every AI tool I used forgot
everything between sessions and I was tired of re-explaining my own
projects to a chatbot.

The other thing that matters to me is that you can see what it's doing.
Every run prints a decision log, basically a trace of what the orchestrator
decided and why. If a run gets blocked or goes weird, the log tells you
where.

The pipeline looks like this:

```
raw input -> intake -> sanitizers -> normalizer -> verifier
          -> orchestrator (experts + tools + memory) -> output filter -> delivery
```

Everything in there is real and running. Two experts (web research and a
writer), four tools (web search, url fetch, calculator, python exec), and
the memory system underneath. Tools don't get raw access to anything, they
go through a handler that does permission checks, SSRF filtering and output
caps. The orchestrator itself is capped at 20 turns and 90 seconds, and
when it hits the cap it has to give you an answer with whatever it has
instead of just timing out.

## Setup

Fastest path: run the installer for your platform (install-linux.sh,
install-macos.sh, install-wsl.sh). It sets up the runtime in docker and
gives you a global `vraksha` command. After that you just need keys in
.env.local (the first run creates it from the template and tells you).

Manual setup if you'd rather not docker the agent itself: Python 3.12,
Docker for the support services, and a Gemini API key.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

docker compose up -d qdrant clamav

# .env.local in the repo root:
#   GOOGLE_API_KEY=...          required
#   ANTHROPIC_API_KEY=...       optional
#   OPENAI_API_KEY=...          optional
#   VRAKSHA_USER_ID=you         optional, defaults to "local-user"
```

Qdrant is the vector store for memory, clamav scans incoming files. The
first run also downloads an embedding model, around 500MB, one time.

A note on keys: a free Gemini key works but Google caps free usage per
model per day. If runs start failing in the evening that's almost
certainly what happened. Every model call has fallbacks configured
(Google then Anthropic then OpenAI), so if you add a funded key for any
of those providers the pipeline will use it automatically when the
primary dies. models.yaml at the root is where all of that is configured.

## Running it

If you used the installer, just type `vraksha` anywhere. It checks docker,
starts the support services and drops you into the TUI: you type briefs at
a prompt, watch a live feed of what the pipeline is doing (which expert
spawned, which tool got called), and get the answer in a panel. Everything
noisier than that goes to vraksha.log next to the repo.

Without the installer it's the same thing via:

```bash
.venv/bin/python main.py
```

Or one-shot if you prefer:

```bash
.venv/bin/python main.py "Briefly research what SSE is best used for, then write a 3-bullet summary."
```

That one does a real web search through the research expert. For tools:

```bash
.venv/bin/python main.py "Use the calculator to compute 47*89, then fetch https://example.com and report its title."
```

And the memory demo, which is the one I'd actually look at if I were you:

```bash
.venv/bin/python main.py "Note for the record: our project codename is BLUEFERN and our launch month is October."
.venv/bin/python main.py "What's our project codename and which month are we launching?"
```

Those are two separate processes. The second one answers from memory.
There's no session being carried over, the fact got embedded and stored in
Qdrant during run 1 and retrieved by similarity in run 2.

Exit code is non-zero when a run blocks or fails, in case you're scripting.

There's also a web dashboard (FastAPI + Next.js) that wraps the same
pipeline with a live-streamed decision log and a UI for browsing memory.

But it's not shipped yet, and I will ship it if this project is successful : )
<!-- 
```bash
.venv/bin/uvicorn server.app:app --port 8000
cd clannon/frontend && npm install && npm run dev
``` -->

## Memory

> It just has a minimal version for now, will move to better one when it becomes successful : )

Four tiers: wiki (user-written, highest trust), semantic (learned facts),
episodic (run history, this is the baseline one), procedural (how you like
things done). All of it lives in shared Qdrant collections and every single
vector carries a user_id in its payload. Reads filter on user_id, no
exceptions, and the only file in the codebase allowed to build a Qdrant
query is core/memory/store.py, so there's no code path where a query
without the user filter even exists. session_id and trace_id ride along in
the payload too, for provenance, so you can trace any memory back to the
run that wrote it.

Retrieval scores by similarity and decays old memories (30 day half life,
they fade but don't disappear). The token budget for hydration gets split
across tiers proportionally to how relevant each tier looks for the query,
with minimum floors so nothing gets starved. Writes go through a policy:
episodic always persists, semantic and procedural need decent confidence,
and nothing the model proposes can ever land in the wiki tier because wiki
is user-authored by definition.

If Qdrant is down, runs still work, just without memory. Hydration returns
empty, writes get dropped, there's a circuit breaker so a dead Qdrant costs
one timeout per 30 seconds and not one per call. Memory was never allowed
to take a run down.

The full design is in core/memory/ARCHITECTURE.md if you want the details.

## When runs get blocked

That's intentional. The verifier screens every input with a small LLM
looking for injection attempts, exfiltration, that category of thing, and
the sanitizers reject dangerous files and unredacted personal data. The
output filter on the other end rejects answers it can't ground in expert
findings or memory. Blocks fail closed and the decision log states the
reason. Normal research briefs pass through fine.

Related: the verifier and output filter models are not user-configurable,
on purpose. Everything else about models is (models.yaml, or per-user
through the web UI), but the two security gates stay pinned because letting
someone downgrade their own guardrails defeats the point of having them.

## What's not in here yet

Billing, multi-tenant Postgres, MCP integrations, the no-signup demo
system, and a background agent that curates memory over time instead of
just accumulating it. All planned, none of it blocks using what's here.

## Layout

```
foundation/   contracts, Flow transport, vocab. imports nothing else
registry/     @tool/@expert registration, model + prompt config
core/         intake, normalizer, verifier, llm adapter, orchestrator, memory
security/     sanitizers (clamav/yara + per-modality workers), output filter
tools/        calculator, web_search, fetch_url, python_exec
experts/      web_research, writer (each bundles its own prompt + skills)
prompts/      system prompts for verifier, orchestrator, filter
main.py       CLI entry
```

One design rule worth knowing if you read the code: nothing between stages
is free-form text. Everything moves as structured payloads through Flow,
and experts return short structured summaries to the orchestrator while
their full findings go to the output filter. The orchestrator never sees
raw expert output. That's what keeps long multi-expert runs from blowing
up its context, and it's also what makes the whole thing auditable.
