# core/

The `core` package contains Vraksha's pipeline spine and the non-security
processing stages that prepare user input for later reasoning.

`core` should describe the request path and own ordinary data preparation. It
should not own shared primitives, security scanners, or provider-specific LLM
calling code.

## What Lives Here

```text
core/
  __init__.py
    Public import surface for active core modules.

  pipeline.py
    Intended full pipeline order and pipeline entry point.

  intake/
    __init__.py
      Exports process().

    intake.py
      First stage: rate limit, size check, modality detection, raw input record.

    rate_limiter.py
      In-memory sliding-window request limiter used by intake.

  normalizer/
    __init__.py
      Exports normalize_payload() and run().

    normalizer.py
      Stage door: picks the modality off the context, delegates to builders,
      stores the result, hands off the Flow. Holds no normalization logic.

    builders.py
      Normalization logic: normalize_payload() + the per-modality builders
      (text/pdf/native/requires-expert). Flow-agnostic and code-only.

    utils.py
      Small payload/text helpers.

    extractors.py
      Format-specific code extractors, currently PDF text extraction.

  verifier/
    __init__.py
      Exports run().

    verifier.py
      Final input gate: deterministic checks, then the verifier LLM.
      (agent.py, checks.py, rules.py, schemas.py, utils.py are internals.)

  llm/
    framework.py
      The ONLY module that imports pydantic_ai. build_agent() + run_structured()
      are the build/run entry points every LLM stage uses; swap or audit the
      framework here. Translates SDK/provider errors to foundation errors.

    registry.py
      Resolves model profiles into Pydantic AI model strings/settings.

    retry.py
      run_agent(): shared transient-error (429/5xx/timeout) retry with
      exponential backoff for every model-calling stage. Fails closed when the
      bounded retry budget is exhausted.

  orchestrator/       PURE orchestration — depends on no specific tool/expert.
    orchestrator.py
      Stage entry point (run). Builds the ports, runs one turn under the
      orchestrator timeout, stores the draft response + memory proposal.
    loop.py
      Hydrate memory, then hand the turn to the gateway (ports.caps.run_turn):
      the orchestrator runs as a NATIVE tool-driving agent — every available
      tool/expert is a guarded native tool. Streams a live decision log via an
      on_event callback; maps the agent's OrchestratorAnswer to OrchestratorResponse.
    schemas.py
      Orchestrator's own contracts: OrchestratorAnswer (the agent's output) +
      DecisionLogEntry. Capability contracts live in registry.capabilities.
    ports.py
      Holds the Capabilities door (caps), the MemoryPort, the decision-log sink.
    utils/
      Internal-only: prompt builder (user message), decision_log sink, wiring.

    The capability machinery + the Capabilities door (which builds & runs the
    native tool-driving turn, bounded, with guards) live in the root `registry/`
    package; the tool/expert impls live in root `tools/` and `experts/`. None of
    it lives here — the orchestrator is given them at runtime via the gateway.

  memory/
    manager.py
      MemoryManager: the single door to the memory layer (implements
      foundation.MemoryPort). Minimal in-memory episodic store for now; real
      Qdrant + fastembed tiers are a dedicated next step.
```

Currently active core stages are:

1. `core/intake/process`
2. `core/normalizer/run`
3. `core/verifier/run`
4. `core/orchestrator/run`

The orchestrator is a Vraksha-owned loop: the model is a structured advisor that
emits one decision per turn; the loop executes it through the Capabilities door
(`ports.caps`), streaming a decision log. Experts and tools are real and register
themselves through the capability registry in the root `registry/` package;
memory is a minimal in-memory episodic store behind the MemoryPort. The output filter (`security/filter`) and delivery
(`delivery/`) run after the orchestrator. The advisor names experts directly; an
entropy-based expert router is a deferred future addition (marked with a TODO in
the loop).

`core/pipeline.py` runs only the active pipeline today. It also documents the
intended later stages: orchestrator, filter, and output, which are not active
exports from `core/__init__.py` yet.

## Import Rule

Core stages use the foundation public surface:

```python
from foundation import Flow, Origin, BlockReason, ThreatLevel
```

Do not import foundation internals unless there is a clear reason. Shared
vocabulary belongs in `foundation`; stage-specific logic belongs in `core` or
the layer that owns it.

## pipeline.py

`pipeline.py` is the intended request spine. Its job is to declare stage order
and run each stage through `Flow.chain()`.

The intended full order is:

```text
raw input
  -> intake
  -> sanitizer
  -> normalizer
  -> verifier
  -> orchestrator
  -> output filter
  -> output
```

The important rule is that every public stage takes and returns a `Flow`:

```python
async def run(flow: Flow) -> Flow:
    ...
```

The pipeline should not contain business decisions. Stage-specific decisions
belong inside the stage. If any stage blocks or fails, `Flow.chain()` skips the
remaining stages automatically.

## Intake

`core/intake/intake.py` is the first active stage.

It:

- Loads the raw payload from `Flow`.
- Checks per-session and global request rate limits.
- Checks the raw input size against `constants.MAX_INPUT_SIZE_BYTES`.
- Detects the input modality: a `str` payload is treated as text directly (never
  a path); byte/file uploads are content-sniffed with `python-magic`, and textual
  `application/*` types (JSON/XML/CSV/YAML/ndjson/x-empty) map to text.
- Writes the original input to `flow.ctx.raw_input`.
- Writes detected modality values to `flow.ctx.detected_modalities`.
- Advances `flow.ctx.current_stage` to `INTAKE`.
- Passes the raw input forward unchanged.

Supported modalities are:

- `text`
- `pdf`
- `image`
- `audio`
- `video`

If input is too large, unsupported, malformed, or rate-limited, intake returns a
blocked `Flow`. It does not call LLMs and does not perform deep security
analysis.

## Rate Limiting

`core/intake/rate_limiter.py` provides the intake request limiter.

It currently uses an in-memory sliding window:

- per-session request window
- global burst window
- bounded tracked-session key count
- thread-safe lock around internal state

The constants live in `foundation/constants.py`:

```python
RATE_LIMIT_WINDOW_S
RATE_LIMIT_MAX_REQUESTS
RATE_LIMIT_MAX_TRACKED_KEYS
GLOBAL_RATE_LIMIT_WINDOW_S
GLOBAL_RATE_LIMIT_MAX_REQUESTS
```

This implementation is fast and appropriate for one process/container. The
limiter is keyed by an `identity` argument (intake passes the session id today;
auth can later pass user_id/IP). When the app runs multiple replicas, replace
the backend with Redis while keeping `check_request_rate(identity)` as the
intake-facing contract.

## Normalizer

`core/normalizer/normalizer.py` is the second active core stage.

It receives the sanitized payload from `security/sanitizers` and creates a
`NormalizedInput`. The stage door delegates the actual work to
`normalize_payload()` in `core/normalizer/builders.py`; the door itself only
picks the modality, stores the result, and hands off the Flow.

The normalizer is code-only:

- no LLM calls
- no provider SDK calls
- no security scanning
- no expensive media conversion unless code extraction is needed

Current behavior:

- Text becomes stable Unicode text (NFKC-normalized; invisible/bidi format
  characters stripped, with ZWJ/ZWNJ preserved for emoji and complex scripts).
- PDF becomes extracted page-aware text using PyMuPDF. A scanned/text-less PDF
  (no extractable text layer) is marked `requires_expert=True` with
  `required_capability="image"` so a later OCR-capable expert handles it.
- Image/audio/video are preserved natively when the target model supports the
  modality.
- Image/audio/video are marked with `requires_expert=True` when the target model
  does not support that modality.

`NormalizedInput` contains:

- `modality`
- `content_type`
- `content`
- `native_payload`
- `target_layer`
- `target_provider`
- `target_model`
- `preserved_native`
- `requires_expert`
- `required_capability`
- `metadata`

The target model is resolved through `foundation.load_model_registry()`, which
reads and caches root `models.yaml`.

## Normalizer Utilities

`core/normalizer/utils.py` contains tiny, dependency-light helpers:

- `payload_to_text()` (decode + `stabilize_unicode()`)
- `stabilize_unicode()`
- `truncate_text()`

Byte coercion is centralized in `foundation.coerce_to_bytes()` (the single
auditable "str is text, never a path" boundary), not duplicated per stage.

`core/normalizer/extractors.py` contains heavier format-specific helpers:

- `extract_pdf_pages()`

Keep core layer decisions in `normalizer.py`. Move utility code out only when it
keeps the stage file cleaner without adding meaningful overhead.

## Boundary With Security

Core does not own the sanitizer layer. The active security cleanup layer lives
in:

```text
security/sanitizers/
```

The boundary is:

1. Intake records raw input and modalities.
2. Sanitizer blocks or returns a sanitized payload.
3. Normalizer turns the sanitized payload into structured input.

Normalizer should not read from raw input by default. It should process the
payload produced by the previous stage.

## Boundary With Foundation

Core depends on `foundation` for:

- `Flow`
- `Origin`
- `BlockReason`
- `ThreatLevel`
- `Modality`
- `PipelineStage`
- shared constants
- model registry access

Foundation must not import from `core`.

## Current Caveats

`core/__init__.py` currently exports:

```python
intake
normalizer
verifier
```

`core/pipeline.py` documents future modules such as orchestrator, filter, and
output, but it does not import them until they exist. Those stages are part of
the intended architecture but are not all implemented/exported yet.

Until those stages exist, test the active path with intake, sanitizers,
normalizer, and verifier directly.
