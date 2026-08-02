# PROTOCOL — `clannon-core` (Rust) ↔ `clannon-ai-runtime` (Python)

Wire reference. No rationale — that is `DECISIONS.md`.

Version `1.0` · HTTP/1.1 · JSON · Rust is the client, Python is the server.

## 0. Boundary

| | Rust `clannon-core` | Python `clannon-ai-runtime` |
|---|---|---|
| Role | client | server |
| Owns | everything else | provider API calls only |
| State | all of it | none — every call is standalone |
| Reachability | public (frontend) | **internal network only** |
| Auth | cookies, users | **none** — protected by unreachability |

**Rule:** does it need a network call to a model provider, or a Python-only ML
ecosystem? → Python. Everything else → Rust. (`DECISIONS.md` D3 + D3a.)

| Capability | Side | Note |
|---|---|---|
| LLM completion | Python | |
| Embeddings | **Rust** | local ONNX (`fastembed`), no network call |
| Reranking | — | does not exist yet |
| Tool execution | Rust | Python never runs a tool |
| Prompt selection | Rust | registry + `locked` live in Rust |
| Loop / turn cap | Rust | |
| Budget reserve/reconcile | Rust | |
| Retries | Rust | Python never retries |

## 1. Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/capabilities` | Handshake. Rust **refuses to start** on mismatch. |
| GET | `/v1/health` | Process up. |
| GET | `/v1/ready` | Credentials load, client constructs. |
| POST | `/v1/complete` | One model call. |

## 2. `GET /v1/capabilities`

| Field | Type | Notes |
|---|---|---|
| `protocol_version` | string | `"1.0"`. Major mismatch → Rust exits. |
| `runtime_version` | string | Informational. |
| `providers` | string[] | `anthropic` · `openai` · `google` |
| `features` | string[] | `structured_output` · `prompt_cache` · `tool_schemas` |

## 3. `POST /v1/complete` — request

| Field | Type | Req | Notes |
|---|---|---|---|
| `request_id` | string | yes | Idempotency + correlation. |
| `trace_id` | string | yes | Run id. **Carries no user identity.** |
| `deadline_ms` | int | yes | Python aborts its own call at this. Rust enforces its own independently. |
| `provider` | enum | yes | Already resolved by Rust. |
| `model` | string | yes | Already resolved. Python does **not** map logical names. |
| `messages` | Message[] | yes | §3.1 |
| `tools` | Tool[] | no | Schemas only. |
| `output_schema` | JSON Schema | no | Present → validated structured output. |
| `params` | Params | no | §3.2 |
| `cache` | Cache | no | §3.3 |

### 3.1 Message

| Field | Type | Notes |
|---|---|---|
| `role` | enum | `system` · `user` · `assistant` · `tool_result` |
| `content` | string | Absent on a pure tool-call assistant turn. |
| `tool_calls` | ToolCall[] | `assistant` only. |
| `tool_call_id` | string | `tool_result` only. |

ToolCall: `id` (string) · `name` (string) · `arguments` (object).

### 3.2 Params

| Field | Type | Notes |
|---|---|---|
| `temperature` | float | |
| `max_output_tokens` | int | Per-call ceiling. |
| `timeout_s` | float | Provider-level; `deadline_ms` still wins. |

### 3.3 Cache

Semantic intent. Python maps to provider parameters; Rust never sends a
provider-specific key.

| Field | Maps to (Anthropic) | Default | Use for |
|---|---|---|---|
| `instructions` | `anthropic_cache_instructions` | true | every layer |
| `tool_definitions` | `anthropic_cache_tool_definitions` | true | every layer |
| `messages` | `anthropic_cache` | false | **multi-turn layers only** (orchestrator, experts) |

`messages: true` on a one-shot layer costs write overhead with nothing to reuse.
Non-Anthropic providers ignore all three.

## 4. `POST /v1/complete` — response

**HTTP 200 unless the runtime itself is broken.** A provider failure is data.

| Field | Type | Notes |
|---|---|---|
| `request_id` | string | Echoed. |
| `outcome` | enum | §4.1 |
| `text` | string\|null | |
| `structured` | object\|null | Validated against `output_schema`. |
| `tool_calls` | ToolCall[] | Non-empty iff `outcome = tool_calls`. |
| `finish_reason` | string | Provider's, informational only. |
| `usage` | Usage | **Mandatory on every outcome, errors included.** §4.2 |
| `provider_latency_ms` | float | |
| `error` | Error\|null | Non-null iff `outcome = error`. §5 |

### 4.1 `outcome`

| Value | Meaning | Rust's move |
|---|---|---|
| `completed` | final text and/or structured | use it |
| `tool_calls` | model wants tools | execute, append `tool_result`, call again |
| `refused` | provider content-policy refusal | surface honestly, **do not retry** |
| `error` | see `error` | branch on `error.class` only |

### 4.2 Usage — the four counters are DISJOINT

| Field | Type |
|---|---|
| `input_tokens` | int |
| `output_tokens` | int |
| `cache_read_tokens` | int |
| `cache_write_tokens` | int |
| `requests` | int |

| Question | Answer |
|---|---|
| Billed volume | `input + output` (cache counters are **separate rates**) |
| Total processed | `input + output + cache_read + cache_write` |
| Cache effectiveness | `cache_read / (cache_read + input)` |

**Never sum all four for cost.** The provider reports them disjointly: a cached prefix
is billed as a write (~1.25×) or a read (~0.1×), not at the input rate. Summing
double-counts.

## 5. Error

| Field | Type | Notes |
|---|---|---|
| `class` | enum | **The only field Rust may branch on.** |
| `retryable` | bool | Advisory. Rust owns the retry decision. |
| `provider_status` | int\|null | HTTP status from the provider. |
| `message` | string | **Never empty.** Falls back to the exception type name. |

### 5.1 `class` — closed enum

| Value | Meaning |
|---|---|
| `rate_limit` | provider throttled |
| `provider_unavailable` | 5xx / connection failure |
| `timeout` | `deadline_ms` hit |
| `invalid_request` | malformed — Rust's bug |
| `content_policy` | provider refused the request itself |
| `auth` | credentials rejected |
| `schema_validation` | output failed `output_schema` |
| `internal` | runtime fault |

> **Never branch on `message`.** A hit spend ceiling was once retried past the ceiling
> because a dependency appended a docs link to an error string and our classifier read
> the prose. `class` exists so the wire carries the decision.

> **`message` is never empty.** `str(exc)` is `""` for exceptions raised without one —
> a live path here is a timeout. Floor is the exception type name.

## 6. Invariants

| # | Invariant | Enforced by |
|---|---|---|
| 1 | Python never retries | Rust owns the retry budget |
| 2 | Python never decides the loop is done | Rust owns `max_turns` |
| 3 | Python never executes a tool | tools carry permissions |
| 4 | Python never chooses a prompt | registry + `locked` are Rust's |
| 5 | Python never receives a user/tenant id | it has no authorization role |
| 6 | Python holds no state between calls | restartable, testable |
| 7 | Python never raises across the wire | typed envelope only |
| 8 | Python is unreachable from outside | compose `expose:`, never `ports:` |
| 9 | `usage` present on every response | budget reconcile needs it |
| 10 | Degradation is Rust's decision | Python reports, never decides |

## 7. Not in v0

| Thing | When |
|---|---|
| Token streaming | `POST /v1/complete/stream`, SSE (`delta`/`tool_call`/`usage`/`done`). Today's report streaming is chunked after the fact, so nothing real is lost. |
| gRPC | Only when measured serialization cost or streaming volume justifies it. |
| Embeddings endpoint | Only if embeddings ever become a hosted API. |
