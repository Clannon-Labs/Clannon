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
      Exports NormalizedInput, normalize_payload(), and run().

    normalizer.py
      Code-only normalization stage.

    utils.py
      Small payload/text helpers.

    extractors.py
      Format-specific code extractors, currently PDF text extraction.
```

Currently active core stages are:

1. `core/intake/process`
2. `core/normalizer/run`

`core/pipeline.py` runs only the active pipeline today. It also documents the
intended later stages: verifier, orchestrator, filter, and output. Those later
core/security stages are not active exports from `core/__init__.py` yet.

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
- Detects the input modality with `python-magic`.
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

This implementation is fast and appropriate for one process/container. When the
app runs multiple replicas, replace the backend with Redis while keeping
`check_request_rate(session_id)` as the intake-facing contract.

## Normalizer

`core/normalizer/normalizer.py` is the second active core stage.

It receives the sanitized payload from `security/sanitizers` and creates a
`NormalizedInput`.

The normalizer is code-only:

- no LLM calls
- no provider SDK calls
- no security scanning
- no expensive media conversion unless code extraction is needed

Current behavior:

- Text becomes normalized Unicode text.
- PDF becomes extracted page-aware text using PyMuPDF.
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

- `payload_to_bytes()`
- `payload_to_text()`
- `truncate_text()`

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

`core/__init__.py` currently exports only:

```python
intake
normalizer
```

`core/pipeline.py` documents future modules such as verifier, orchestrator,
filter, and output, but it does not import them until they exist. Those stages
are part of the intended architecture but are not all implemented/exported yet.

Until those stages exist, test the active path with intake, sanitizers, and
normalizer directly.
