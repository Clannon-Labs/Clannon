# Rust features and crates — mapped onto Clannon

**Not a tutorial.** Every entry says *use X here, for this reason, in this subsystem*.
Nothing recommended because it is simple; where the powerful option costs more, that
cost is stated and the powerful option still wins.

**On crate freshness:** verify current versions and maintenance before adopting — this
was written 2026-08-02 and a crate recommendation ages faster than a design decision.
Where a crate's maturity is genuinely uncertain, it says so rather than guessing.

---

## Part 1 — Language features, by what they buy us

### 1.1 Type-state for `Flow` — the biggest single win

LAW 3 says `Flow` is the only inter-stage transport and stages run in order. In Python
that is a convention plus tests. In Rust it is the compiler.

```rust
struct Flow<S> { ctx: Context, journal: Vec<JournalEntry>, _stage: PhantomData<S> }

struct Intake; struct Sanitized; struct Normalized; struct Verified;

impl Flow<Intake>     { fn sanitize(self) -> Result<Flow<Sanitized>, Blocked> {…} }
impl Flow<Sanitized>  { fn normalize(self) -> Result<Flow<Normalized>, Blocked> {…} }
impl Flow<Normalized> { fn verify(self)   -> Result<Flow<Verified>, Blocked> {…} }
```

| Bug class this deletes | Today |
|---|---|
| Running the orchestrator on unsanitized input | prevented by review + tests |
| Advancing a blocked flow | runtime `should_stop` check |
| Skipping the verifier | nothing structural stops it |
| Reading the payload after `offload()` | runtime `RuntimeError` |

Each becomes a compile error. `PhantomData<S>` is zero-sized — no runtime cost.

**Cost, honestly:** generic structs infect signatures, and anything that must hold "a
flow at some stage" needs an enum wrapper or `Box<dyn>`. Worth it: this is the
architecture's central invariant.

### 1.2 Newtypes for every id — tenant isolation, compiler-enforced

`user_id`, `run_id`, `session_id`, `project_id`, `memory_id` are all `str` today. The
type system cannot tell you passed the wrong one.

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct UserId(String);
```

The `user_id` payload filter is the single most security-critical invariant in the
codebase (ADR-0002, §V.20). A newtype makes "passed a `RunId` where a `UserId` was
required" unrepresentable. Combine with §1.7.

### 1.3 Enums with data — make illegal states unrepresentable

The output filter's contract has *consistency rules* written in prose: `proceed: true`
implies `blocked: false`, `reason: null`, `categories: []`. That is a prose rule
because the Python shape allows the contradiction.

```rust
pub enum FilterVerdict {
    Proceed { groundedness: Groundedness },
    Blocked { reason: String, categories: Vec1<Category>, groundedness: Groundedness },
}
```

A blocked verdict without a reason no longer compiles. Same pattern for run status,
completion state, and `outcome` in `PROTOCOL.md`.

**Where this pays most:** the three axes we deliberately keep separate — `status`,
`verificationState`, `completionState`. Three enums, never collapsible into a bool.

### 1.4 RAII / `Drop` for budget reservations

A reserved budget that is never reconciled leaks the reservation. Python needs
`try/finally` discipline at every call site.

```rust
pub struct Reservation { id: ReservationId, broker: Arc<dyn BudgetPort>, settled: bool }

impl Drop for Reservation {
    fn drop(&mut self) {
        if !self.settled { self.broker.release_unsettled(self.id); }
    }
}
```

A panic, an early return, a cancelled task — the reservation still releases. This is
strictly stronger than what the Python can offer, and money is where it matters.

Pair with `#[must_use]` so ignoring a reservation is a warning.

### 1.5 Traits for ports, sealed so nobody adds a back door

`foundation/contracts/` becomes traits. Seal them: a port is *our* boundary, and an
external impl would be a way around the single-door rule.

```rust
mod private { pub trait Sealed {} }

#[async_trait]
pub trait MemoryPort: private::Sealed + Send + Sync {
    async fn hydrate(&self, req: HydrationRequest) -> HydrationPackage;
}
```

`dyn Trait` where the implementation is swapped at runtime (that is the whole point of
LAW 6); `impl Trait` / generics on hot paths where monomorphisation is free.

### 1.6 `thiserror` for typed errors, `#[non_exhaustive]` so adding one is not breaking

LAW 5: typed errors never swallowed. `PROTOCOL.md` §5.1's closed enum is exactly this.

```rust
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum RuntimeError {
    #[error("rate limited by {provider}")]        RateLimit { provider: Provider },
    #[error("deadline exceeded after {elapsed:?}")] Timeout { elapsed: Duration },
}
```

**`thiserror` in libraries, `anyhow` only at the top-level binary.** Using `anyhow`
inside a subsystem throws away the type information the caller needs to branch — which
is the exact mistake the pydantic-ai money-guard incident punished us for.

The `Display` impl is also where the never-empty-message rule (`f3a347e`) becomes
structural: a variant with no message cannot be constructed.

### 1.7 `PhantomData` for a scope token — authorization you cannot forget

```rust
pub struct Scoped<T, S = Unauthorized> { inner: T, _scope: PhantomData<S> }
```

Only `authorize(user_id)` produces `Scoped<T, Authorized>`, and only that type reaches
the store. "Fetch then check" stops being expressible. Zero runtime cost.

### 1.8 `rust_decimal` for money — never `f64`

Budget arithmetic in binary floating point silently loses cents. Use `Decimal`
everywhere money exists, and a newtype (`Usd`) on top so it cannot be added to a
token count.

### 1.9 Other features worth reaching for

| Feature | Where | Why |
|---|---|---|
| `#[must_use]` | `Result`, `Reservation`, `Flow` | ignoring one is a bug, not a style choice |
| `Cow<'_, str>` | sanitizer output | most inputs are unmodified — avoid cloning them |
| `Arc<str>` | prompts, tool schemas | shared immutable, cheaper than `Arc<String>` |
| `bytes::Bytes` | payload handles | cheap slicing without copying upload bytes |
| `tokio::sync::Semaphore` | sanitizer worker cap | replaces the concurrency-limit bookkeeping |
| `CancellationToken` | run cancel | structured cancellation the whole tree observes |
| `serde(deny_unknown_fields)` | every wire type | an unexpected field is a contract drift signal |
| `schemars` | tool schemas, `output_schema` | derive JSON Schema *from* the type — one source of truth |
| `typed-builder` / builder + typestate | run construction | required fields enforced at compile time |

---

## Part 2 — Crates, by what they replace

### 2.1 Direct replacements for our Python dependencies

| Python today | Rust | Note |
|---|---|---|
| `nh3` | **`ammonia`** | `nh3` *is* Python bindings to `ammonia`. Rust removes a layer. |
| `fastembed` | **`fastembed-rs`** | same model, same ONNX path |
| ONNX runtime | **`ort`** | if `fastembed-rs` is too high-level |
| `tiktoken` | **`tiktoken-rs`** / **`tokenizers`** | `tokenizers` is HF's, written in Rust with Python bindings |
| `qdrant-client` | **`qdrant-client`** | official Rust client |
| `redis` | **`redis`** (async) or **`fred`** | Lua `EVAL` supported by both — the atomic broker survives |
| `kuzu` | **`kuzu`** | Kuzu ships a Rust API; the Python package wraps C++ |
| `PyYAML` | **`serde_yml`** / **`serde_norway`** | ⚠️ `serde_yaml` is archived — check which fork is alive before choosing |
| `orjson` | **`serde_json`** | equivalent or faster; `simd-json` if profiling demands |
| `httpx` | **`reqwest`** | |
| `fastapi` + `uvicorn` | **`axum`** + `tokio` | SSE is `axum::response::sse`, multipart built in |
| `structlog` | **`tracing`** + `tracing-subscriber` | spans map onto our journal model better than logging does |
| `opentelemetry-sdk` | **`opentelemetry`** + `tracing-opentelemetry` | |
| `tenacity` | **`backon`** | |
| `cachetools` | **`moka`** | async-aware, TTL, better than a hand-rolled LRU |
| `jsonschema` | **`jsonschema`** | pair with `schemars` for generation |
| `cryptography` | **`ring`** / **`aes-gcm`** + **`argon2`** | memory encryption at rest, password hashing |
| `python-magic` | **`infer`** | content-type sniffing |
| `Pillow` | **`image`** + **`kamadak-exif`** | metadata stripping |
| `pymupdf` / `pikepdf` | **`lopdf`** / **`pdf`** | ⚠️ weaker than the Python pair — evaluate before committing |
| `yara-python` | **`yara-rust`** | bindings to the same libyara |
| `clamd` | **`clamav-client`** | or hand-roll: the socket protocol is trivial |
| `uvloop` | — | not needed; `tokio` is the runtime |
| `anyio` | — | not needed; `tokio` |

### 2.2 Crates that replace code we hand-wrote

This is the more interesting list — where a crate deletes our own maintenance burden.

| Our code | Crate | What disappears |
|---|---|---|
| retry/backoff in `core/llm/retry.py` | **`backon`** | jitter, ceilings, per-attempt budget |
| circuit breaker (memory, ClamAV) | **`failsafe`** | breaker state machine, half-open probes |
| per-worker + total timeouts | `tokio::time::timeout` | the nested-deadline bookkeeping in the sanitizer runner |
| concurrency caps | `tokio::sync::Semaphore` | worker-slot accounting |
| in-process caches | **`moka`** | TTL, eviction, stampede protection |
| rate limiting | **`governor`** | GCRA, more correct than a token bucket we write |
| config loading + validation | **`figment`** + `serde` + **`garde`** | layered YAML/env merge, and fail-loud validation with floors — the D8 "config must never weaken a defense" rule becomes a `#[garde(range(min = …))]` attribute |
| SSE framing | `axum::response::sse` | manual `data: {json}\n\n` assembly |
| decision-log dedup / ordering | `indexmap` | insertion-ordered maps without a parallel list |

### 2.3 Testing — where Rust is genuinely better than what we have

| Need | Crate | Note |
|---|---|---|
| Property-based tests | **`proptest`** | the concurrent budget interleavings in `CONFORMANCE_HARNESS.md` Layer 2 want this, not hand-written cases |
| Snapshot tests | **`insta`** | prompt-composition and API-shape assertions |
| Parametrised tests | **`rstest`** | |
| HTTP mocking | **`wiremock`** | provider-failure paths |
| Benchmarks | **`criterion`** | statistically honest, unlike a stopwatch |
| Fuzzing | **`cargo-fuzz`** | the sanitizer is the obvious target; we have none today |
| Deterministic async testing | **`turmoil`** / `tokio::time::pause` | test a 10s timeout in microseconds |
| Concurrency-bug detection | **`loom`** | exhaustively explores interleavings — for the budget broker specifically |

**`loom` and `proptest` on the budget broker are the strongest argument in this
document for Rust being safer, not just faster.** Neither has a real Python equivalent,
and money under concurrency is exactly the thing we cannot test properly today.

### 2.4 What Rust does NOT need

Under `DECISIONS.md` D2, Python makes the provider calls. So **Rust needs no LLM SDK** —
no `async-openai`, no Anthropic client. That is a real simplification and a reason the
boundary is drawn where it is: provider churn stays in the small Python worker.

---

## Part 3 — The gap this research actually found

**Presidio has no Rust equivalent, and this breaks the boundary rule as written.**

`security/sanitizers/` PII detection is `presidio-analyzer` + `presidio-anonymizer` over
spaCy's `en_core_web_lg`. It is local ML inference — no network call — so
`DECISIONS.md` D3 says *Rust*. There is no Rust Presidio, and there will not be one.

Three options, in order of preference:

| Option | What it means | Verdict |
|---|---|---|
| **Refine the rule** | Python owns anything needing a Python-only ML ecosystem. Embeddings still go Rust (`fastembed-rs` exists); Presidio stays Python. | **Recommended** — smallest change, keeps the rule truthful |
| Port spaCy NER to ONNX + `ort` | Possible for the NER model, but Presidio is recognizers, context enhancement and anonymization on top, not just NER | Large, and reimplements a security-critical component |
| Drop Presidio | Weakens PII detection | No |

**The refined rule:** *does it need a network call to a provider, **or** a
Python-only ML ecosystem? → Python. Everything else → Rust.*

That keeps embeddings in Rust for the right reason (a Rust path genuinely exists) and
puts Presidio in Python for the right reason (one genuinely does not) — rather than
having a rule that quietly does not survive contact with the second subsystem.

**Consequence for the architecture:** the Python side is not purely a model-call
worker. It is a *Python-ecosystem worker* with two capabilities: provider calls, and
local ML that only exists in Python. `PROTOCOL.md` would gain a `POST /v1/analyze_pii`
endpoint at the point `security/` is ported (Phase 3 item 3), not before.

Also affected, same reasoning, to check when their turn comes: `detect-secrets`,
`RestrictedPython` (sandboxed Python execution stays Python by definition), and
`faster-whisper` for audio transcription.
