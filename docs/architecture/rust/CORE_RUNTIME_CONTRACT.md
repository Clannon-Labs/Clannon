# The `clannon-core` ↔ `clannon-ai-runtime` contract

**Status:** `[PROPOSED]` — owner ruling 2026-08-02 settled the direction and the
boundary rule. This document turns that ruling into an exact wire contract. Nothing
is built. Read `RUST_MIGRATION_STRATEGY.md` first for how a port happens at all, and
`CONFORMANCE_HARNESS.md` for how either side is proven to satisfy this.

---

## 1. The one rule

> **Python makes calls to models. Rust does everything else.**

That is the owner's rule and it is sharper than any list of module names, so the rule
is normative and the module list below is only its consequence. When a new component
appears, ask the rule, not the list.

`clannon-core` (Rust) — the service. Owns the pipeline, flow, intake, normalizer,
verifier, sanitizers, output filter, registry, prompts, tools, experts, orchestration,
memory, budgets, persistence, audit, **and the HTTP/SSE API the frontend talks to.**

`clannon-ai-runtime` (Python) — a worker. Owns exactly one capability: *given a fully
prepared request, call a model provider and return what came back.*

### The test for "does this belong in Python?"

**Does it make a network call to a model provider?** If no, it is Rust — even if it
"touches a model."

This matters immediately for embeddings. `core/memory/embeddings.py:2` is
`fastembed nomic-embed-text-v1.5`, **local ONNX inference** — the ~500MB is a one-time
model download, and inference then runs in-process with no network call. Under the
rule, embeddings are **Rust-side** (`fastembed-rs` / `ort`). Putting them in Python
would turn five in-process calls per turn into five network hops
(`hydration.py:83`, `deep_reader.py:212`, `curator.py:92`, `write_policy.py:222`,
`write_policy.py:477`) and buy nothing.

Reranking appears in the owner's sketch but **does not exist yet** — zero non-test
matches in the tree. Do not draft contract surface for it. When it arrives, apply the
rule: a local cross-encoder is Rust, a hosted rerank API is Python.

---

## 2. Who drives the agent loop — the load-bearing decision

pydantic-ai owns the agent loop today: tool dispatch, structured-output validation,
retries, and usage accounting. Rust owning "tools" and "experts" while Python owns
"agents" therefore has two possible readings, and they are very different systems.

**Option A — Python drives the loop and calls back into Rust for each tool.**
Keeps pydantic-ai as designed. Makes Python the orchestrator and Rust its tool server,
which inverts the owner's intent, and requires bidirectional RPC.

**Option B — Rust drives the loop; Python performs ONE model call per request.**
Python is stateless. Rust holds the conversation, executes tools, counts turns, spends
budget, and decides when to stop.

**We take Option B**, and not only because it matches the stated intent.

> On 2026-08-01 our bounded-loop money guard was found to be broken because
> pydantic-ai 2.18 appended a docs link to `UsageLimitExceeded`'s message and our
> classifier read that *text* to decide whether a failure was transient. A hit spend
> ceiling was classified as a rate limit and **retried past the ceiling it exists to
> enforce.** No API changed; a sentence moved.

LAW 6 names this exactly: *if an invariant is enforced only by the dependency, we
outsourced a promise, not isolated a dependency.* Option B moves the loop cap, the
spend ceiling and the stop decision into Rust, where we own them. That is the
strongest argument for this split — stronger than performance — and it should be the
reason quoted when someone later proposes moving the loop back into Python for
convenience.

**Consequence to accept honestly:** we give up pydantic-ai's multi-turn machinery and
reimplement turn management in Rust. Single-call use of pydantic-ai still buys us
provider abstraction, request/response shaping, structured-output validation and
usage extraction — which is the part that is genuinely hard and provider-specific.

---

## 3. Transport

**HTTP/1.1 + JSON for v0.** Not gRPC.

`RUST_MIGRATION_STRATEGY.md` §"Cross-language boundary" already settled this: start
with HTTP/JSON when inspectability matters, adopt gRPC only when measured volume or
streaming justifies its operational cost. The owner's motive here is *comprehension* —
being able to `curl` a boundary and read the answer is worth more right now than
protobuf's type safety, and the JSON Schema in §5 recovers most of that safety anyway.

Revisit gRPC when either is true: measured serialization cost is material, or token
streaming across the boundary becomes the normal path.

**Addressing.** Python binds an internal interface only. Under Docker Compose it is
`expose:`, never `ports:` — it must not be publishable. Rust reaches it by service
name (`http://ai-runtime:50051`); Docker's internal DNS resolves it, so no IP is ever
managed by hand. Locally the dev scripts bind it to `127.0.0.1`.

**Trust model.** The runtime has **no authentication** and therefore **must be
unreachable from outside the compose network.** Anyone who can reach it can spend
provider money. This is a deployment invariant, not a nice-to-have, and it belongs in
the deploy checklist as a hard gate.

---

## 4. What Python must never do

These are the guarantees Rust keeps. A runtime that takes any of them on is a bug,
because it silently moves an invariant back across the boundary.

| Python must never | Because |
|---|---|
| Retry a failed call | Rust owns the retry budget and the spend ceiling |
| Decide the loop is finished | Rust owns `max_turns` and the stop condition |
| Execute a tool | Tools carry permissions; Rust owns least-privilege |
| Choose a prompt | The registry and `locked: true` live in Rust |
| See a user id or tenant id | It has no authorization role; it should not hold identity |
| Hold conversation state between calls | Statelessness is what makes it restartable and testable |
| Raise an exception across the wire | Every failure is a typed envelope (§6) |

The identity line is a deliberate privacy choice: the runtime receives an opaque
`trace_id` for correlation and nothing that identifies a user. Message content still
crosses, so this limits blast radius rather than eliminating it.

---

## 5. Surface — v0

Four endpoints. Version in the path; breaking changes take `/v2`.

### `GET /v1/capabilities`

Rust calls this at startup and **refuses to start** on mismatch (fail-closed).

```json
{
  "protocol_version": "1.0",
  "runtime_version": "0.1.0",
  "providers": ["anthropic", "openai", "google"],
  "features": ["structured_output", "prompt_cache", "tool_schemas"]
}
```

### `GET /v1/health` and `GET /v1/ready`

`health` = process is up. `ready` = provider credentials load and the client
constructs. Rust surfaces both in its own readiness so a half-up stack cannot look
healthy — the failure mode that produced the ClamAV incident on 2026-07-29.

### `POST /v1/complete` — the whole product, essentially

One model call. Stateless. Rust prepares everything.

```json
{
  "request_id": "req_01H...",
  "trace_id": "run_7722d656692a",
  "deadline_ms": 30000,
  "provider": "anthropic",
  "model": "claude-haiku-4-5",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "tool_calls": [{"id": "t1", "name": "web_search", "arguments": {}}]},
    {"role": "tool_result", "tool_call_id": "t1", "content": "..."}
  ],
  "tools": [{"name": "web_search", "description": "...", "input_schema": {}}],
  "output_schema": {},
  "params": {"temperature": 0.0, "max_output_tokens": 2048},
  "cache": {"instructions": true, "tool_definitions": true}
}
```

Notes that are easy to get wrong:

- `provider` and `model` are **already resolved**. Rust owns the registry; the runtime
  never maps a logical name, because that mapping is policy.
- `tools` are **schemas only**. The runtime declares them to the provider and returns
  requested calls. It never executes one.
- `deadline_ms` is a hard local deadline. The runtime aborts its own provider call at
  the deadline and returns a `timeout` error envelope. Rust also enforces its own
  deadline independently — neither side trusts the other's clock.
- `cache` carries prompt-cache intent, mapping onto pydantic-ai's
  `anthropic_cache_instructions` / `anthropic_cache_tool_definitions`. Caching is
  already configured today (`core/llm/registry.py:198-209`); this keeps it working
  across the boundary rather than silently dropping it.

**Response — always HTTP 200 unless the runtime itself is broken.** Provider failures
are data, not transport errors, because Rust must be able to distinguish "the model
refused" from "the runtime is down."

```json
{
  "request_id": "req_01H...",
  "outcome": "completed",
  "text": "...",
  "structured": null,
  "tool_calls": [],
  "finish_reason": "stop",
  "usage": {
    "input_tokens": 1840,
    "output_tokens": 220,
    "cache_read_tokens": 1600,
    "cache_write_tokens": 0
  },
  "provider_latency_ms": 1420,
  "error": null
}
```

`outcome` is one of:

| outcome | meaning | Rust's move |
|---|---|---|
| `completed` | final text and/or validated structured output | use it |
| `tool_calls` | model wants tools run | execute, append results, call again |
| `refused` | provider content-policy refusal | surface honestly, do not retry |
| `error` | see `error` envelope | classify by `error.class`, never by prose |

**`usage` is mandatory on every outcome, including errors**, or Rust cannot reconcile
a budget reservation for a call that partially spent. `cache_read_tokens` /
`cache_write_tokens` must be reported separately — they were being discarded from every
accounting path until `2547696` fixed it, and the boundary is an easy place to lose
them again.

---

## 6. Errors, timeouts, degradation

```json
{
  "error": {
    "class": "rate_limit",
    "retryable": true,
    "provider_status": 429,
    "message": "TimeoutError"
  }
}
```

`class` is a **closed enum**, and it is the only thing Rust is allowed to branch on:

`rate_limit` · `provider_unavailable` · `timeout` · `invalid_request` ·
`content_policy` · `auth` · `schema_validation` · `internal`

> **Never classify on `message`.** This is the same defect as the 2.18
> `UsageLimitExceeded` incident, one layer out: a provider changing its error prose
> must never change our control flow. The `class` field exists so the wire carries the
> decision, not the prose.

**`message` must never be empty.** `str(exc)` is `''` for every exception raised
without one — the live path in the Python codebase is a sanitizer worker timeout, and
it produced a fail-closed gate whose recorded reason was blank (fixed in `f3a347e`
via `_describe_error`). The runtime applies the same floor: fall back to the exception
type name. A boundary that can report a failure without saying what failed is worse
than one that crashes.

**Degradation is Rust's decision, always.** The runtime reports; it never decides the
run should continue without something. This mirrors the rule memory already follows —
every fault degrades with an honest note, and the honesty is the point.

---

## 7. Streaming — deliberately not in v0

Today's "streaming" report is a single pass chunked after the fact, not genuinely
progressive. So v0 is request/response, and we lose nothing real.

When true streaming is built it is `POST /v1/complete/stream` returning SSE with
`delta` / `tool_call` / `usage` / `done` events, and Rust re-emits to the frontend on
its own SSE surface. Doing it later is cheap; doing it now would fix a protocol around
a UX we have not designed.

---

## 8. Repository and process layout

```
services/
  core/            # Rust — cargo workspace
  ai-runtime/      # Python — clannon_ai package
dev/
  run-core.sh      # Rust service alone
  run-runtime.sh   # Python runtime alone
  run-backend.sh   # both, wired
  run-frontend.sh  # frontend alone
  dev.sh           # backend + frontend — the one command
```

This is the owner's structure. The root `dev.sh` today already owns dependency
startup and readiness for ClamAV and Qdrant; that logic moves into
`dev/run-backend.sh` rather than being rewritten, because it encodes real incidents
(a healthy-looking frontend over a backend failing closed at an absent ClamAV).

---

## 9. What contradicts this and must be corrected

`RUST_MIGRATION_STRATEGY.md` lines 162-164 currently say *"TypeScript continues to
call the Python API over HTTP/WebSocket. Rust stays behind Python-owned application
contracts."* The owner's 2026-08-02 ruling **inverts** that: Rust owns the API the
frontend talks to. That doc and `docs/ROADMAP.md` §3 ("Status: deferred, not started")
are now wrong and must be updated in the same commit that ratifies this contract — a
stale strategy doc is exactly what an agent will follow.

---

## 10. Open questions for the owner

1. **Does the frontend contract change at all?** Cheapest path is Rust serving the
   *identical* HTTP/SSE surface, so the frontend never learns which language answered
   and `sse_contract_drift.py` keeps enforcing. Recommended.
2. **Migration order.** Contract-first (build the boundary inside today's Python, so
   `core/llm/` becomes a client of a local runtime *before* any Rust exists) means the
   boundary is proven in production before it is also a language boundary. Recommended
   — it separates two risks that are otherwise taken together.
3. **Does the runtime own provider keys, or does Rust inject them per call?** Runtime
   owning them is simpler and keeps secrets in one process; Rust injecting them makes
   the runtime fully stateless. Recommend runtime-owned.
