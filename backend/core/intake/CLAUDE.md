# core/intake/ — the first raw-input gate

Owns the cheap admission checks before any expensive work: per-session + global
rate limiting, raw input size limit, MIME/modality detection. First active stage.

## NEVER
- No LLM calls; no deep security analysis. Intake decides *what* the payload is
  and *whether* it may enter the sanitizer layer — nothing more. Threat inspection
  belongs to `security/sanitizers`.
- A `str` payload is text, NEVER a filesystem path (invariant §IV.19 — coercion
  centralized in `foundation.coerce_to_bytes`). Byte/file uploads are
  content-sniffed with libmagic (`python-magic`), NEVER trusted by file extension.
- Don't reach forward into later stages' context. Write only `raw_input`,
  `detected_modalities`, and advance the stage; pass the raw input forward unchanged.

## Conventions
- `intake.py` is the door; `rate_limiter.py` is an in-memory sliding window keyed
  by an `identity` arg (session id today; auth can later pass user_id/IP). At
  multi-replica, swap the backend for Redis but keep `check_request_rate(identity)`
  as the intake-facing contract.
- Limits live in `foundation/constants.py` (`RATE_LIMIT_*`, `GLOBAL_RATE_LIMIT_*`,
  `MAX_INPUT_SIZE_BYTES`). Supported modalities: text, pdf, image, audio, video.
- Too-large / unsupported / malformed / rate-limited → a blocked `Flow`.

## Tests
`tests/intake.py`.

## Authoritative docs
`core/README.md` → Intake / Rate Limiting; `foundation/FLOW_GUIDE.md` → Intake.
