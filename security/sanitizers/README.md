# Sanitizers Module

The sanitizers module is the pipeline's security cleanup layer. Its job is to
inspect incoming payloads before later stages touch them, block clearly unsafe
inputs, and pass forward a sanitized payload when a worker can clean the input
without damaging quality.

The active path is:

1. `security/sanitizers/runner.py`
2. `security/sanitizers/pre_sanitization.py`
3. `security/sanitizers/workers/*`

## Sanitizer Runner

`runner.py` is the stage entry point used by the pipeline.

It:

- Loads the payload from the current `Flow`.
- Advances `flow.ctx.current_stage` to `SANITIZING`.
- Runs universal pre-sanitization first.
- Runs modality-specific sanitizer workers only after pre-sanitization passes.
- Runs matching modality workers concurrently, under a global concurrency limit
  (`SANITIZER_MAX_WORKERS`) and a per-worker timeout (`SANITIZER_TIMEOUT_WORKER_S`),
  within an overall total timeout.
- Blocks the flow when a worker reports a blocking threat level (and persists the
  worker report to `flow.ctx.sanitization` on that block path too).
- Blocks if intake somehow reports no modality with a matching worker.
- Stores sanitizer results in `flow.ctx.sanitization`.
- Passes the sanitized payload to the next stage when a worker produced one.

The original input is not destroyed by this stage. The default downstream
payload becomes the sanitized output, but sanitizer reports and context keep the
stage-level details available for inspection.

On success, `flow.ctx.sanitization` is a dictionary with:

- `pre_sanitization`: the ClamAV/YARA aggregate result.
- `workers`: modality worker results.
- `sanitized_outputs`: sanitized payloads keyed by modality.

On sanitizer block, `flow.ctx.sanitization_blocked` is set to `True` and
`flow.ctx.sanitization_block_reason` stores the internal reason.

## Pre-Sanitization

`pre_sanitization.py` is the universal gate that runs before text, image, PDF,
audio, or video workers.

It currently uses:

- ClamAV through the `clamd` Python client.
- YARA through `yara-python`.

ClamAV and YARA run concurrently on the same payload bytes. ClamAV scans through
the clamd TCP `INSTREAM` API (the Python code connects to an already-running
clamd service; it does not start the daemon). YARA compiles local `.yar`/`.yara`
files from the configured rules directory once and caches the compiled rules,
recompiling only when the rule files change.

If the YARA rules directory is missing, it is created automatically. If no rules
exist, YARA skips with a clean result in development; in production (env-gated by
`VRAKSHA_ENV` / `AGENT_REQUIRE_YARA`) a missing rule set fails closed.

Relevant environment variables:

```env
CLAMAV_HOST=127.0.0.1
CLAMAV_PORT=3310
AGENT_YARA_DIR=rules
```

In Docker Compose, ClamAV runs as its own service and the app points to it with:

```env
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
AGENT_YARA_DIR=/vraksha/rules
```

## Text Worker

`workers/text.py` handles text payloads.

It uses:

- `detect-secrets` to detect API keys, tokens, and credentials.
- `presidio-analyzer` to detect PII.
- `presidio-anonymizer` to anonymize detected PII.

Secrets are treated as high risk and can block the pipeline. PII is anonymized
into `sanitized_text` when found. HTML is intentionally not stripped or escaped:
the text sink is an LLM (not a browser), so markup carries no injection risk
here, and escaping `<`/`>`/`&` would corrupt ordinary text and code. XSS
protection belongs to the output filter at render time.

The async `scan()` function is only the entry point. The actual blocking work is
done in `_scan_sync()` and moved to a worker thread so the runner can keep other
modality workers concurrent.

## Image Worker

`workers/image.py` handles image payloads.

It uses:

- Pillow to validate image structure and dimensions.
- `exiftool` to strip metadata without recompressing image pixels.

The worker rejects invalid images and decompression bombs. When metadata exists,
it strips metadata losslessly and returns `sanitized_image`. `exiftool` runs
under a subprocess timeout so a crafted image cannot hang the worker.
If metadata stripping fails (or times out) after validation, the worker preserves
the validated original image rather than degrading visual quality through a
forced re-encode.

## PDF Worker

`workers/pdf.py` handles PDF payloads.

It uses:

- PyMuPDF (`fitz`) for page-count validation.
- `pikepdf` for structural parsing, dangerous-entry stripping, and safe re-save.

It blocks encrypted PDFs that cannot be inspected, invalid PDFs, and PDFs that
exceed the configured page limit. It strips active PDF features such as
JavaScript actions, launch actions, embedded files, rich media, and XFA/forms
before returning `sanitized_pdf`.

## Audio Worker

`workers/audio.py` handles audio payloads.

It uses:

- `ffmpeg`/`ffprobe` through `ffmpeg-python` to validate and remux audio.
- `mutagen` to inspect audio metadata.

It rejects inputs without an audio stream and blocks audio that exceeds the
configured duration limit. Metadata stripping is done through stream-copy remux
when possible, preserving audio quality instead of re-encoding. The remux runs
under a hard timeout (run-async + kill) so a crafted file cannot hang ffmpeg.
If remuxing fails (or times out) after validation, the worker preserves the
validated original payload rather than lowering quality with a fallback transcode.

## Video Worker

`workers/video.py` handles video payloads.

It uses:

- `ffmpeg`/`ffprobe` through `ffmpeg-python` to validate and remux video.

It rejects inputs without a video stream and blocks video that exceeds the
configured duration limit. Metadata stripping is done through stream-copy remux
when possible, preserving video quality instead of re-encoding. The remux runs
under a hard timeout (run-async + kill) so a crafted file cannot hang ffmpeg.
If remuxing fails (or times out) after validation, the worker preserves the
validated original payload rather than lowering quality with a fallback transcode.

## Runtime Dependencies

Python dependencies for this layer live in `requirements.txt`.

System dependencies needed by the active sanitizer workers are installed in the
Docker image:

- `ffmpeg`
- `libimage-exiftool-perl`
- `libmagic1`

ClamAV runs as a separate Docker Compose service instead of inside the app
container.

## Tests

Current sanitizer tests live in:

- `tests/text_sanitization.py`
- `tests/pre_sanitization.py`
- `tests/sanitizer_runner.py`

Run the whole suite with:

```bash
python -m pytest tests/
```

The ClamAV EICAR test requires a running clamd daemon. If clamd is not
available, that test is skipped.

## Not Active In The Pipeline

`security/vendors/pdfid/` contains standalone Didier Stevens PDF tools. They are
not imported by the active sanitizer pipeline.

They can be useful for manual PDF investigation, but the working PDF sanitizer
currently uses `PyMuPDF` and `pikepdf` because those provide structured Python
APIs that are easier to test and integrate.
