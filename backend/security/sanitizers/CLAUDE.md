# security/sanitizers/ — the input security cleanup layer

Owns the security gate before normalized reasoning: a universal malware pre-scan,
then per-modality cleanup workers. One `Flow` in, one `Flow` out.

## NEVER
- Pre-sanitization (ClamAV + YARA) runs FIRST, before any modality worker touches
  the bytes. A high/critical threat blocks before the orchestrator can ever see the
  payload. Don't run a worker ahead of the pre-gate.
- Uploaded INPUT files (`uploads.py` / `scan_upload`) get the malware pre-gate
  ONLY — a clean file is admitted with its ORIGINAL bytes, never redacted or
  anonymized (the expert needs full fidelity). Do NOT run the redacting modality
  workers on uploads; don't nerf media. (The brief text path still gets full worker
  sanitization.)
- Fail closed: if a gate can't run, reject. In prod a missing YARA rule set fails
  closed (`VRAKSHA_ENV` / `AGENT_REQUIRE_YARA`).
- Don't destroy the original input; keep worker reports on `ctx.sanitization`.
- The text worker does NOT strip/escape HTML — the sink is an LLM, not a browser,
  and escaping would corrupt code/text. XSS protection is the output filter's job
  at render time. Secrets block; PII is anonymized into `sanitized_*`.

## Conventions
- `runner.py` (door) → `pre_sanitization.py` → `workers/*` (text=detect-secrets +
  presidio; image=Pillow + exiftool; pdf=PyMuPDF + pikepdf; audio/video=ffmpeg
  remux). Concurrency `SANITIZER_MAX_WORKERS`, per-worker timeout
  `SANITIZER_TIMEOUT_WORKER_S`. Standalone `security/vendors/pdfid/` is NOT in the
  active path.

## Tests
`tests/pre_sanitization.py`, `tests/text_sanitization.py`, `tests/sanitizer_runner.py`, `tests/uploads.py`.

## Authoritative docs
`security/sanitizers/README.md`; `docs/architecture/SYSTEM_ARCHITECTURE.md` → Sanitization.
