# Security

> **Purpose:** Entry point for Clannon's layered, fail-explicit security model —
> the gates every input and output passes through.
> **Scope:** Intake limits, sanitization (ClamAV/YARA + modality workers), the
> verifier, the output filter, tool permissioning, tenancy isolation, and the
> threat model. Token-budget atomicity lives in [../storage/](../storage/);
> memory write trust lives in [../memory/](../memory/).
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> Security rules in [../../vision/INVARIANTS.md](../../vision/INVARIANTS.md) (§IV–V)
> are Tier 1 and outrank everything here.
> **Related:** [../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)
> (Critical Benchmark 5) · [../agents/](../agents/) · [../../glossary/TERMS.md](../../glossary/TERMS.md)

## Canonical design

This subsystem's authoritative text is distributed across
[../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md):

- **Security Model** — the layered stance and the explicit block / fail / warn
  rule; the "all fetched content is untrusted" rule; identity-set-once; RLS.
- **Intake** — first raw-input gate (rate limit, size, MIME/modality detection).
- **Sanitization** — universal pre-gate (ClamAV/YARA) + parallel modality
  workers (text/PDF/image/audio/video).
- **Verification** — the verifier LLM: the sole *input* content blocker;
  structured output only; replaced LLM Guard + Rebuff (see ADR
  [../../decisions/rejected/0006-external-prompt-screening-libraries.md](../../decisions/rejected/0006-external-prompt-screening-libraries.md)).
- **Output Filter** — the sole *output* gate before delivery.

> Upload-input posture nuance: uploaded **input files** are malware-scanned
> (ClamAV/YARA) and their original bytes are seeded — clean data is never
> redacted and media is never nerfed. The user *brief* still gets full
> sanitization. Keep these two paths distinct.

## Order of the gates (security before execution)

```
intake → sanitize → normalize → verify → orchestrator → output filter → delivery
```

Security failures **block**. Infrastructure/config failures **fail hard**.
Warnings proceed only when the downstream layer can safely handle the risk.

## Implementation

- `backend/core/intake/`, `backend/security/sanitizers/`,
  `backend/core/verifier/`, `backend/security/filter/`.
- Locked prompts (verifier, filter) load from the out-of-git `prompts.secure/`
  overlay and fail closed in production if still on baselines.

## Validation

The adversarial bar is **Critical Benchmark 5** in
[../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md](../../benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md):
detect, classify, explain, prevent compromise, preserve audit trail.
