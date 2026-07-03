"""Critical Benchmark 3 — Unified Multi-Modal Representation: cross-reference probe.

Assembles a tiny same-project fixture corpus — a markdown doc, a small PDF, an
image carrying text, and a source file, every one of them naming ONE shared
entity (``MarrowgateIndex``) — runs each through the REAL intake -> sanitizer ->
normalizer preprocessing, and reports a per-modality table of which modalities
ingested and whether the shared entity STRING survives into the normalized
content across them.

It maps a structured PASS / PARTIAL / NOT-YET read onto C3's pass requirements:

    shared-entities · cross-media-relationships · provenance · contradictions ·
    unified-knowledge

plus an ``ingest`` precondition that is the one capability actually built today.

What this probe MEASURES (and what it deliberately does NOT)
-----------------------------------------------------------
C3's objective is that "media becomes knowledge rather than isolated summaries":
shared entities created across PDFs/images/markdown/source, cross-media relations,
contradiction detection, one unified knowledge object. NONE of that exists in code
— it is Pillar 2 / ADR 0005 (PROPOSED, unbuilt). This harness therefore certifies
only the PRECONDITION and measures the distance to convergence; it MUST NOT, and
does NOT, build any knowledge graph, shared-entity object, or cross-media link.

What it certifies hermetically:

  * INGESTION. All four fixtures are admitted by intake (libmagic modality
    detection on the raw upload bytes — fed as bytes, not str, so the detection
    ladder actually runs), pass the sanitizer, and are normalized by the EXISTING
    code-only normalizer. Three distinct modalities are exercised: text (markdown
    + source both detect as text/plain), pdf, and image.
  * CROSS-MODALITY STRING PRESENCE. After preprocessing, the shared entity string
    is present in the normalized ``content`` of the markdown, the PDF (PyMuPDF text
    layer), and the source — 3 of 4 — and ABSENT from the image, because code-only
    normalization does not OCR: the image ingests as a native / media-expert
    handoff with empty text content. That absence is the honest gap, not a bug.

The honest NOT-YET, by design:

  * SHARED ENTITIES / CROSS-MEDIA RELATIONSHIPS / CONTRADICTIONS / UNIFIED
    KNOWLEDGE are NOT-YET. The probe shows the raw material co-occurs across
    modalities, but the system creates no unified entity, no relationship, and no
    contradiction check — that convergence is ADR 0005, gated on the maintainer.
  * PROVENANCE is PARTIAL: per-ITEM ingestion provenance exists (each
    ``NormalizedInput`` records its modality, content_type and media handoff, and
    the Flow journal records every stage's origin/status), but there is no
    entity -> source cross-media provenance, because no entities are created.

Hermetic seams (the same doubles the existing security tests use):

  * the ClamAV/YARA pre-gate -> a clean ``PreSanitizationResult``.
  * the detect-secrets / Presidio text sub-workers -> clean stubs (so Presidio's
    spaCy model is never loaded). The PDF (pikepdf/PyMuPDF) and image (Pillow)
    workers run for real; the fixture image carries no metadata, so exiftool is
    never invoked. No network, no model download, no paid key.

Run:
    pytest tests/benchmarks/c3_multimodal.py -q          # acceptance tests
    PYTHONPATH=tests python -m benchmarks.c3_multimodal  # from backend/, prints report

``run()`` returns the ``BenchmarkReport`` for the consolidated scoreboard harness.
"""

from __future__ import annotations

import asyncio
import io
from contextlib import ExitStack
from dataclasses import dataclass, field
from unittest.mock import patch

from foundation import Flow
from core.intake import intake, rate_limiter
from core.normalizer import normalizer
from security.sanitizers import pre_sanitization, runner
from security.sanitizers.pre_sanitization import PreSanitizationResult
from security.sanitizers.workers import text as text_worker
from security.sanitizers.workers.text import TextWorkerResult

try:  # package context (pytest collects this as benchmarks.c3_multimodal)
    from .report import BenchmarkReport, Verdict
except ImportError:  # direct-path context (backend/tests/benchmarks on sys.path[0])
    from report import BenchmarkReport, Verdict


# The single entity every fixture names. A distinctive CamelCase token that is also
# a valid identifier (so the source fixture uses it as a class name) and never a
# stopword, so a substring match across modalities is unambiguous, not coincidence.
SHARED_ENTITY = "MarrowgateIndex"

# The modalities a real same-project corpus spans. markdown + source both detect as
# the `text` modality; pdf and image are distinct — three modalities, four files.
_TEXT_KINDS = ("markdown", "source")


# --------------------------------------------------------------------------
# Fixture corpus — each builder returns the raw UPLOAD BYTES for one file, every
# one naming SHARED_ENTITY. Fed as bytes (not str) so intake's libmagic modality
# detection runs; a str payload would force TEXT and collapse the multi-modal probe.
# Generation is deterministic and uses only libraries the normalizer/sanitizer
# already depend on (PyMuPDF, Pillow), so the corpus needs no committed binaries.
# --------------------------------------------------------------------------
def _markdown_bytes() -> bytes:
    return (
        f"# {SHARED_ENTITY} design notes\n\n"
        f"The {SHARED_ENTITY} coordinates retrieval across the memory tiers.\n"
        f"It is the shared entity that ties this project's documents together.\n"
    ).encode("utf-8")


def _source_bytes() -> bytes:
    return (
        f'"""Reference implementation of the {SHARED_ENTITY}."""\n\n'
        f"class {SHARED_ENTITY}:\n"
        f"    \"\"\"Ranks memory hits for the project.\"\"\"\n\n"
        f"    def rank(self, items):\n"
        f"        return sorted(items)\n"
    ).encode("utf-8")


def _pdf_bytes() -> bytes:
    """A one-page PDF with a real text layer naming the shared entity (PyMuPDF)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"{SHARED_ENTITY} architecture overview")
    page.insert_text((72, 100), f"The {SHARED_ENTITY} unifies every modality of this project.")
    data = doc.tobytes()
    doc.close()
    return data


def _image_bytes() -> bytes:
    """A small PNG that CARRIES the shared entity as drawn text (no metadata, so the
    image worker's exiftool step is never reached)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (360, 90), "white")
    ImageDraw.Draw(img).text((10, 35), f"{SHARED_ENTITY} system diagram", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _corpus() -> list[tuple[str, bytes]]:
    """The fixture corpus as (fixture-kind, upload-bytes) pairs, in report order."""
    return [
        ("markdown", _markdown_bytes()),
        ("pdf", _pdf_bytes()),
        ("image", _image_bytes()),
        ("source", _source_bytes()),
    ]


# --------------------------------------------------------------------------
# Hermetic doubles (only the external-engine seams; the modality workers run real).
# --------------------------------------------------------------------------
async def _clean_pre_sanitization(_raw):
    """Stand in for the ClamAV/YARA pre-gate: clean, so the path stays hermetic."""
    return PreSanitizationResult()


def _clean_secrets_worker(_text: str) -> TextWorkerResult:
    return TextWorkerResult(name="detect-secrets")


def _clean_pii_worker(_text: str) -> TextWorkerResult:
    """Clean PII verdict, so Presidio's spaCy model is never loaded (hermetic)."""
    return TextWorkerResult(name="presidio")


def _reset_rate_limiters() -> None:
    """Evaluate each fixture as an independent first request (the global burst limit
    would otherwise be a shared-state confounder across the corpus)."""
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()


# --------------------------------------------------------------------------
# Per-fixture outcome.
# --------------------------------------------------------------------------
@dataclass
class ModalityProbe:
    kind: str                       # fixture kind: markdown / pdf / image / source
    detected_modality: str = ""     # intake's libmagic modality (text/pdf/image/...)
    ingested: bool = False          # admitted + sanitized + normalized (not halted)
    stopped_stage: str = ""         # "" if ingested, else where the flow halted
    reason: str | None = None       # block/fail reason code if halted
    content_type: str = ""          # NormalizedInput.content_type
    content_chars: int = 0          # length of the normalized text content
    entity_present: bool = False    # SHARED_ENTITY is a substring of normalized content
    preserved_native: bool = False  # media kept natively for a capable model
    requires_expert: bool = False   # routed to a media expert (e.g. OCR/vision)
    required_capability: str | None = None

    @property
    def is_text_kind(self) -> bool:
        return self.kind in _TEXT_KINDS

    @property
    def media_handoff(self) -> bool:
        """True when the item ingested as a non-text MEDIA handoff (native or expert)
        rather than as extracted text — the shape the image takes."""
        return self.preserved_native or self.requires_expert


@dataclass
class Outcome:
    probes: list[ModalityProbe] = field(default_factory=list)

    def by_kind(self, kind: str) -> ModalityProbe | None:
        return next((p for p in self.probes if p.kind == kind), None)


async def _probe_one(kind: str, payload: bytes) -> ModalityProbe:
    """Drive one fixture through the REAL intake -> sanitizer -> normalizer path."""
    _reset_rate_limiters()
    probe = ModalityProbe(kind=kind)

    flow: Flow = Flow.new(payload, session_id=f"c3-{kind}")
    flow = await intake.process(flow)
    if flow.ctx.detected_modalities:
        probe.detected_modality = flow.ctx.detected_modalities[0]
    if flow.should_stop:
        probe.stopped_stage = "intake"
        probe.reason = flow.reason
        return probe

    flow = await runner.run(flow)
    if flow.should_stop:
        probe.stopped_stage = "sanitizer"
        probe.reason = flow.reason
        return probe

    flow = await normalizer.run(flow)
    if flow.should_stop:
        probe.stopped_stage = "normalizer"
        probe.reason = flow.reason
        return probe

    normalized = flow.ctx.normalized_input
    content = normalized.content or ""
    probe.ingested = True
    probe.content_type = normalized.content_type
    probe.content_chars = len(content)
    probe.entity_present = SHARED_ENTITY in content
    probe.preserved_native = normalized.preserved_native
    probe.requires_expert = normalized.requires_expert
    probe.required_capability = normalized.required_capability
    return probe


async def _ingest_corpus() -> Outcome:
    out = Outcome()
    for kind, payload in _corpus():
        out.probes.append(await _probe_one(kind, payload))
    return out


def _run() -> tuple[Outcome, BenchmarkReport]:
    with ExitStack() as stack:
        stack.enter_context(patch.object(pre_sanitization, "run", _clean_pre_sanitization))
        stack.enter_context(patch.object(text_worker, "_secrets_worker", _clean_secrets_worker))
        stack.enter_context(patch.object(text_worker, "_pii_worker", _clean_pii_worker))
        outcome = asyncio.run(_ingest_corpus())
    return outcome, _build_report(outcome)


# --------------------------------------------------------------------------
# Requirement scoring -> structured report.
# --------------------------------------------------------------------------
def _build_report(o: Outcome) -> BenchmarkReport:
    report = BenchmarkReport(
        benchmark_id="C3",
        title="Unified Multi-Modal Representation",
        requirement_summary=(
            "ingest / shared-entities / cross-media-relationships / provenance / "
            "contradictions / unified-knowledge"
        ),
    )

    ingested = [p for p in o.probes if p.ingested]
    modalities = sorted({p.detected_modality for p in ingested})
    text_present = [p for p in ingested if p.is_text_kind and p.entity_present]
    pdf_probe = o.by_kind("pdf")
    image_probe = o.by_kind("image")
    present_kinds = [p.kind for p in ingested if p.entity_present]
    absent_kinds = [p.kind for p in ingested if not p.entity_present]

    # --- ingest: every modality is admitted + preprocessed (the built capability) -
    if len(ingested) == len(o.probes) and len(modalities) >= 3:
        report.add_requirement(
            "ingest", "Ingest each modality (precondition)", Verdict.PASS,
            f"all {len(o.probes)} fixtures were admitted by intake, passed the "
            f"sanitizer, and were normalized by the existing code-only normalizer, "
            f"spanning {len(modalities)} modalities ({', '.join(modalities)}).",
            tuple(f"{p.kind}: modality={p.detected_modality} ctype={p.content_type}"
                  for p in ingested))
    else:
        halted = [p for p in o.probes if not p.ingested]
        report.add_requirement(
            "ingest", "Ingest each modality (precondition)", Verdict.FAIL,
            f"{len(halted)}/{len(o.probes)} fixtures did not ingest "
            f"(modalities seen: {', '.join(modalities) or 'none'}); the multi-modal "
            "preprocessing precondition is not met.",
            tuple(f"{p.kind}: stopped@{p.stopped_stage} reason={p.reason}" for p in halted))

    # --- shared-entities: the raw material co-occurs, but no entity is CREATED -----
    # The probe proves the shared entity STRING survives into the normalized content
    # of the text-class modalities; it intentionally creates no unified entity.
    matrix = "; ".join(
        f"{p.kind}({p.detected_modality})="
        f"{'present' if p.entity_present else 'absent'}" for p in o.probes)
    report.add_requirement(
        "shared_entities", "Create shared entities across media", Verdict.NOT_YET,
        f"the shared entity '{SHARED_ENTITY}' survives ingestion into the normalized "
        f"content of {len(text_present)} text-class fixtures and "
        f"{'the PDF' if (pdf_probe and pdf_probe.entity_present) else 'no PDF'} "
        f"({len(present_kinds)}/{len(o.probes)}: {', '.join(present_kinds) or 'none'}), and is "
        f"absent from {', '.join(absent_kinds) or 'none'} "
        "(code-only normalization does not OCR the image). The string co-occurs across "
        "modalities, but the system creates NO unified entity object linking these "
        "occurrences. Entity creation/linking is Pillar 2 / ADR 0005 (unbuilt); this "
        "harness MEASURES the precondition and does not build it.",
        (matrix,))

    # --- cross-media-relationships: none built (and the task forbids building one) -
    report.add_requirement(
        "cross_media_relationships", "Build cross-media relationships", Verdict.NOT_YET,
        "no relationships, edges, or knowledge graph are built across the modalities; "
        "each fixture normalizes to an independent NormalizedInput handoff. Cross-media "
        "linking is ADR 0005 (unbuilt) and is explicitly out of scope for this probe.")

    # --- provenance: per-ITEM ingestion provenance yes; entity->source no ----------
    report.add_requirement(
        "provenance", "Track provenance", Verdict.PARTIAL,
        "per-item ingestion provenance exists: each ingested item carries its detected "
        "modality, content_type and media-handoff metadata on the NormalizedInput, and "
        "the Flow journal records every stage's origin and status. Marked PARTIAL "
        "because there is NO entity -> source cross-media provenance (which entity came "
        "from which media), since no entities are created — that is gated on ADR 0005.",
        tuple(f"{p.kind}: modality={p.detected_modality}, ctype={p.content_type}"
              for p in ingested))

    # --- contradictions: no claim/contradiction detection across media -------------
    report.add_requirement(
        "contradictions", "Identify contradictions across sources", Verdict.NOT_YET,
        "no claim extraction or cross-source contradiction detection exists; the "
        "fixtures are deliberately consistent and nothing compares them. Contradiction "
        "detection over unified knowledge is ADR 0005 (unbuilt).")

    # --- unified-knowledge: media stays per-modality isolated handoffs --------------
    report.add_requirement(
        "unified_knowledge", "Produce unified knowledge (not isolated summaries)",
        Verdict.NOT_YET,
        "each modality becomes its own NormalizedInput handoff (text content for "
        "markdown/pdf/source, a native/expert media handoff for the image) — isolated "
        "per-modality representations, which is exactly the 'isolated summaries' state "
        "C3's objective contrasts against. Converging them into one unified knowledge "
        "object is Pillar 2 / ADR 0005 (unbuilt); this harness MUST NOT and does not "
        "build it.")

    # --- per-modality presence table -----------------------------------------------
    for p in o.probes:
        if not p.ingested:
            report.add_case(p.kind, "STOPPED",
                            f"modality={p.detected_modality or '∅'} "
                            f"stopped@{p.stopped_stage} reason={p.reason}")
            continue
        if p.entity_present:
            entity = "entity=PRESENT"
        elif p.media_handoff:
            handoff = "native" if p.preserved_native else f"expert:{p.required_capability}"
            entity = f"entity=ABSENT (media handoff [{handoff}]; no OCR)"
        else:
            entity = "entity=ABSENT"
        report.add_case(
            p.kind, "ingested",
            f"modality={p.detected_modality} ctype={p.content_type} "
            f"chars={p.content_chars} {entity}")

    # --- honesty notes -------------------------------------------------------------
    report.add_note(
        f"cross-modality presence of '{SHARED_ENTITY}' after the EXISTING normalizer + "
        f"sanitization preprocessing: present in [{', '.join(present_kinds) or 'none'}], "
        f"absent in [{', '.join(absent_kinds) or 'none'}] "
        f"({len(present_kinds)}/{len(o.probes)} fixtures, {len(modalities)} modalities).")
    report.add_note(
        "the image carries the entity as drawn text but ingests as a "
        "native/media-expert handoff with empty text content: code-only normalization "
        "does not OCR, so its text is not surfaced here (it would require the vision "
        "expert). That is an honest gap, not a defect.")
    report.add_note(
        "true entity CONVERGENCE — shared entities, cross-media relationships, "
        "contradiction detection, one unified knowledge object — is NOT-YET: Pillar 2 / "
        "ADR 0005 is PROPOSED and unbuilt. This harness measures the distance to it and "
        "builds NO knowledge graph.")
    report.add_note(
        "hermetic doubles: a clean ClamAV/YARA pre-gate and clean detect-secrets / "
        "Presidio text sub-workers (so spaCy never loads). The real intake (libmagic), "
        "sanitizer (pikepdf/PyMuPDF/Pillow) and code-only normalizer (PyMuPDF text "
        "extraction) run unchanged. No network, model download, or paid key.")
    report.add_note("serves Critical Benchmark 3 and Pillar 2 (unified multi-modal representation).")
    return report


# --------------------------------------------------------------------------
# Cached single run (the ingest is identical across tests).
# --------------------------------------------------------------------------
_CACHE: tuple[Outcome, BenchmarkReport] | None = None


def results() -> tuple[Outcome, BenchmarkReport]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _run()
    return _CACHE


def run() -> BenchmarkReport:
    """Public entry point for the consolidated scoreboard / standalone use."""
    return results()[1]


# --------------------------------------------------------------------------
# pytest acceptance tests.
# --------------------------------------------------------------------------
def test_all_four_modalities_ingest_across_at_least_three_modalities():
    outcome, report = results()
    assert len(outcome.probes) == 4, "the corpus must hold exactly four fixtures"
    for p in outcome.probes:
        assert p.ingested, (
            f"{p.kind} did not ingest (stopped@{p.stopped_stage}, reason={p.reason})"
            f"\n{report.render()}")
    detected = {p.detected_modality for p in outcome.probes}
    # markdown + source detect as text; pdf and image are distinct -> >= 3 modalities.
    assert {"text", "pdf", "image"} <= detected, f"modalities seen: {detected}"


def test_shared_entity_string_is_present_across_the_text_class_modalities():
    outcome, report = results()
    # markdown, the PDF (PyMuPDF text layer), and the source all carry the entity
    # string into their normalized content — genuine cross-modality presence.
    for kind in ("markdown", "pdf", "source"):
        p = outcome.by_kind(kind)
        assert p is not None and p.ingested
        assert p.entity_present, (
            f"{kind}: shared entity '{SHARED_ENTITY}' missing from normalized content"
            f"\n{report.render()}")
        assert p.content_chars > 0


def test_image_text_is_not_surfaced_by_code_only_preprocessing():
    """The honest gap: the image ingests, but as a native/media-expert handoff with no
    extracted text, so the entity it visually carries is absent (no OCR here)."""
    outcome, _ = results()
    img = outcome.by_kind("image")
    assert img is not None and img.ingested, "the image fixture must still ingest"
    assert img.detected_modality == "image"
    assert img.media_handoff, "the image must ingest as a native/expert media handoff"
    assert not img.entity_present, "code-only preprocessing must not surface image text"
    assert img.content_chars == 0


def test_report_maps_c3_requirements_and_marks_convergence_not_yet():
    _, report = results()
    keys = {r.key for r in report.requirements}
    assert keys == {"ingest", "shared_entities", "cross_media_relationships",
                    "provenance", "contradictions", "unified_knowledge"}, keys
    by_key = {r.key: r for r in report.requirements}
    # the one built capability is a genuine PASS...
    assert by_key["ingest"].verdict is Verdict.PASS, "\n" + report.render()
    # ...per-item provenance is PARTIAL...
    assert by_key["provenance"].verdict is Verdict.PARTIAL, "\n" + report.render()
    # ...and every true-convergence requirement is honestly NOT-YET, never faked PASS.
    for key in ("shared_entities", "cross_media_relationships",
                "contradictions", "unified_knowledge"):
        assert by_key[key].verdict is Verdict.NOT_YET, f"{key}\n" + report.render()
    # no requirement is a genuine defect; PARTIAL is the honest overall read.
    assert not report.has_failure(), "\n" + report.render()
    assert report.overall() is Verdict.PARTIAL


def test_no_knowledge_graph_or_shared_entity_object_is_built():
    """C3's hard constraint: MUST NOT build a knowledge graph. Structurally encode it
    — every convergence requirement stays NOT-YET, and the only cross-modality artifact
    the harness produces is the presence TABLE (a measurement over independent
    NormalizedInput handoffs), never a linked entity/relationship structure."""
    outcome, report = results()
    convergence = ("shared_entities", "cross_media_relationships",
                   "contradictions", "unified_knowledge")
    by_key = {r.key: r for r in report.requirements}
    for key in convergence:
        assert by_key[key].verdict is Verdict.NOT_YET, key
    # the probe outputs are independent per-fixture rows, not a graph: no probe links
    # to another, and the report carries no entity/relationship structure beyond the
    # flat presence cases.
    assert all(isinstance(p, ModalityProbe) for p in outcome.probes)
    assert len(report.cases) == len(outcome.probes)


def test_report_renders_the_cross_modality_presence_table():
    _, report = results()
    rendered = report.render()
    assert "BENCHMARK C3" in rendered
    assert "OVERALL:" in rendered
    assert "NOT-YET" in rendered  # convergence gaps are visible
    # the presence table names every fixture and the shared entity verdict
    for kind in ("markdown", "pdf", "image", "source"):
        assert kind in rendered
    assert "entity=PRESENT" in rendered and "entity=ABSENT" in rendered
    assert SHARED_ENTITY in rendered


def main() -> int:
    report = run()
    print(report.render())
    return 1 if report.has_failure() else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
