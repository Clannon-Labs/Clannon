# core/normalizer/ — sanitized payload → NormalizedInput (code-only)

Owns turning the sanitized payload into the structured `NormalizedInput` contract
that later stages reason over.

## NEVER
- CODE-ONLY (invariant §IV.16): no LLM calls, no provider SDK, no security
  scanning, no expensive media conversion beyond code extraction. If you're
  tempted to call a model here, the work belongs in an expert.
- Don't force everything to text — "don't nerf the agent." Produce a structured
  representation; preserve safe native handles when the target model can use them,
  else mark `requires_expert=True` + `required_capability` for later routing.
- Resolve target-model capability via the model registry, but make NO final
  security judgment — that's the verifier's job.
- Don't read `raw_input` by default; process the previous stage's sanitized payload.

## Conventions
- The stage door (`normalizer.py`) only picks the modality off context, stores the
  result, hands off the Flow — it holds no normalization logic. Logic lives in
  `builders.py` (per-modality: text/pdf/native/requires-expert), heavier
  format-specific extraction in `extractors.py` (PyMuPDF PDF text), tiny helpers
  in `utils.py`.
- Text → NFKC-stable Unicode (strip invisible/bidi format chars; keep ZWJ/ZWNJ for
  emoji/complex scripts). Scanned/text-less PDF → `requires_expert=True`,
  `required_capability="image"` (an OCR-capable expert handles it later).

## Tests
`tests/normalizer.py`.

## Authoritative docs
`core/README.md` → Normalizer; `foundation/FLOW_GUIDE.md` → Normalization.
