# Repository Structure (Reference Target)

> **Purpose:** A reference target directory tree for a clean production layout.
> **Scope:** Backend/frontend deploy split and per-layer file placement.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** reference target, **not** the live map. For "where is the code
> today," the project root `CLAUDE.md` → "Repository Layout" is authoritative and
> wins on conflict. See [README.md](README.md).
> **Related:** [README.md](README.md) · [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md)
> → Architectural Conventions.

---

> Adapt this to our current working structure cleanly instead of blindly following.

> Like dont create new files if not neeeded (if not needed tho, do it if needed)

> And put things in right places as i would have to deploy backend and api to railway
> and frontend to vercel

> Ofc you know more than me, so do what production grade systems do

clannon/
│
├── backend/                           ← Railway deploys this
│   │
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── .env.example
│   │
│   ├── foundation/                    ← shared primitives, no business logic
│   │   ├── __init__.py
│   │   ├── flow.py                    ← Flow.load/next/block/warn/fail
│   │   ├── context.py                 ← FlowContext, session identity
│   │   ├── schemas.py                 ← NormalizedInput, VerificationResult, etc.
│   │   ├── enums.py                   ← PipelineStage, ThreatLevel, BlockReason, Origin
│   │   └── models.yaml                ← model registry / capability profiles
│   │
│   ├── core/
│   │   └── llm/                       ← PydanticAI behind clannon adapter
│   │       ├── __init__.py
│   │       ├── framework.py           ← build_agent + run_structured (ONLY entry point)
│   │       ├── registry.py            ← resolve model profiles → callable configs
│   │       ├── clients.py             ← construct provider clients
│   │       ├── schemas.py             ← Pydantic output schemas
│   │       ├── verifier_agent.py      ← structured verifier LLM
│   │       └── errors.py              ← translate provider errors → foundation errors
│   │
│   ├── pipeline/                      ← the agent loop, stage by stage
│   │   ├── __init__.py
│   │   ├── intake.py                  ← rate limit, size check, MIME detect
│   │   ├── normalizer.py              ← code-only, no LLM calls
│   │   ├── verifier.py                ← LLM semantic gate, structured output only
│   │   └── output_filter.py           ← final gate before delivery
│   │
│   ├── sanitizers/                    ← parallel modality workers
│   │   ├── __init__.py
│   │   ├── universal.py               ← ClamAV + YARA (runs first, on everything)
│   │   ├── text.py                    ← secrets, PII, HTML cleanup
│   │   ├── pdf.py                     ← structure validation, strip dangerous features
│   │   ├── image.py                   ← parser validation, metadata stripping
│   │   ├── audio.py                   ← validation, metadata, duration limits
│   │   └── video.py                   ← validation, metadata, duration limits
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── loop.py                    ← clannon-owned loop, model is advisor only
│   │   ├── decisions.py               ← OrchestratorDecision, DecisionLogEntry
│   │   └── entropy_router.py          ← Shannon entropy expert spawning
│   │
│   ├── experts/
│   │   ├── __init__.py
│   │   ├── base.py                    ← ExpertSummary + ExpertFindings contracts
│   │   ├── research.py
│   │   ├── code.py
│   │   ├── documentation.py
│   │   ├── media.py
│   │   ├── data_analysis.py
│   │   └── citation.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── handler.py                 ← permission check (PermissionLevel) + sandbox
│   │   ├── web_search.py
│   │   ├── web_fetch.py
│   │   ├── code_exec.py               ← sandboxed execution
│   │   └── file_read.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── port.py                    ← MemoryPort interface (ONLY public surface)
│   │   ├── stub.py                    ← Macondo stub (hydrate returns empty)
│   │   ├── manager.py                 ← real Memory Manager (post-Macondo)
│   │   ├── retriever.py               ← deterministic scoped read, no LLM
│   │   ├── hydrator.py                ← builds hydration package for orchestrator
│   │   ├── write_agent.py             ← governed write, off hot path
│   │   ├── curator.py                 ← background consolidation
│   │   └── tiers/
│   │       ├── wiki.py                ← R2-backed markdown, highest trust
│   │       ├── semantic.py            ← Qdrant, facts + relationships
│   │       ├── episodic.py            ← Qdrant, task history + decisions
│   │       └── procedural.py          ← Qdrant, skills + preferences
│   │
│   ├── delivery/                      ← platform adapters, no reasoning here
│   │   ├── __init__.py
│   │   ├── base.py                    ← DeliveryAdapter interface
│   │   ├── web.py                     ← dashboard / SSE streaming
│   │   └── background.py              ← async job dispatch + progress tracking
│   │
│   ├── integrations/                  ← MCP + external platforms (post-Macondo)
│   │   ├── __init__.py
│   │   └── mcp/
│   │       └── adapter.py             ← MCP data enters sanitization, never bypasses
│   │
│   ├── db/                            ← database layer
│   │   ├── __init__.py
│   │   ├── client.py                  ← Supabase/Postgres connection
│   │   ├── redis.py                   ← Upstash Redis singleton
│   │   └── migrations/
│   │
│   └── api/                           ← FastAPI HTTP surface, thin layer only
│       ├── __init__.py
│       ├── main.py                    ← FastAPI app init
│       ├── dependencies.py            ← auth, current_user, user_id injection
│       └── routes/
│           ├── __init__.py
│           ├── run.py                 ← POST /run → pipeline entry
│           ├── auth.py                ← login, session
│           ├── memory.py              ← wiki read/write endpoints
│           └── health.py              ← GET /health
│
├── frontend/                          ← Vercel deploys this
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── (dashboard)/
│   │       ├── run/
│   │       └── memory/
│   ├── components/
│   └── lib/
│       └── api.ts                     ← typed HTTP client for backend
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     ← Semgrep + tests on every push
│       └── deploy.yml
│
├── .semgrepignore
├── semgrep.yaml                       ← unscoped Qdrant query rule (post-Macondo)
└── README.md