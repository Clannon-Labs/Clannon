"""
Critical Benchmark 3 (companion) — Knowledge-Web Convergence Substrate Probe

Why this is a SEPARATE file, not an edit to ``c3_multimodal.py``
------------------------------------------------------------------
The ratified knowledge-web design (proposals/archive/to-backend/
2026-07-06_knowledge-web-design-cb2-cb3-eb3.md §5) says CB3's real proof
"extends ``c3_multimodal.py`` ... Once the memory extractor (§3.1) AND media
extractor (§3.4) both feed the graph." §3.4 (the automatic PDF/audio/video ->
MediaSegment extraction pipeline) does not exist yet — that gate is not met.

``c3_multimodal.py`` also has an exact-key-set assertion on its requirements
(``test_report_maps_c3_requirements_and_marks_convergence_not_yet``) and a
test whose entire purpose is structural: ``test_no_knowledge_graph_or_
shared_entity_object_is_built``. Both were written when ADR 0005's graph
engine (Kuzu, behind GraphPort) was not yet ratified — editing that file now
would either break another concern's certified invariant or silently
contradict a test named for the exact thing this probe does. Neither is
appropriate for a substrate that is real today but whose media-extraction
GATE genuinely is not met. This file proves what the substrate supports NOW,
additively, without touching ``c3_multimodal.py``'s existing certification.

What this probe proves (and does NOT)
--------------------------------------
Two paths write independently into the SAME knowledge-web graph, both naming
``SHARED_ENTITY``:

  1. **The REAL memory extractor.** One ASSUMPTION-kind memory is written
     through the actual ``core.memory.manager.MemoryManager.
     record_write_proposals`` -> ``write_policy._write_graph_twin`` ->
     ``writer.extract_entities`` -> ``GraphManager.write()`` path, unchanged.
     Only the Qdrant store, the embedder, and the entity-extraction LLM call
     are doubled (same hermetic-seam discipline as every benchmark harness —
     no network, no model download, no paid key; mirrors ``c1_memory.py``'s
     ``_FakeStore``/deterministic-embedder convention).
  2. **A HAND-SEEDED MediaSegment node.** Written directly through
     ``GraphManager.write()`` — NOT through any extraction pipeline, because
     none exists. This SIMULATES what §3.4's not-yet-built media extractor
     would eventually produce from a real transcript/PDF/image. It is
     labeled as synthetic everywhere it appears in this file and in the
     report below.

It then reads back through the real port (``members()``/``edges_of()``) and
checks: did both paths' ``RELATES_TO`` edges converge onto the SAME single
``ENTITY`` node (§1.1's convergence-by-canonical-name rule), exercised
end-to-end rather than merely asserted at the unit level (``tests/
memory_knowledge_store.py`` already covers the raw store mechanics; this is
the port-level, cross-origin proof)?

Honest scoring (LAW 6 — never fake a pass): a hand-seeded MediaSegment is NOT
real media ingestion. Every requirement whose own wording says
"media"/"cross-media" is capped at PARTIAL here, never PASS, regardless of
what the mechanism proves — only the graph-substrate-specific claim
(canonical-name convergence across two different origin types) can be PASS.
Automatic media ingestion itself (§3.4) is scored NOT-YET; this file builds
no extractor for it.

Run:
    cd backend && .venv/bin/python -m pytest tests/benchmarks/c3_knowledge_web_convergence.py -v
    PYTHONPATH=tests python -m benchmarks.c3_knowledge_web_convergence   # prints report

``run()`` returns the ``BenchmarkReport``. Not yet wired into
``scripts/benchmarks/run_all.py``'s fixed one-module-per-id C3 slot (that
slot stays pointed at ``c3_multimodal.py``, the ingestion-precondition proof)
— this is an additive companion probe, run standalone for now.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import core.memory.embeddings as embeddings_mod
import core.memory.graph_store as graph_store_mod
import core.memory.store as store_mod
import core.memory.writer as writer_mod
from core.memory.graph_manager import GraphManager
from core.memory.manager import MemoryManager
from foundation import (
    EdgeLabel,
    EdgeOrigin,
    GraphEdge,
    GraphNode,
    GraphScope,
    MemoryKind,
    MemoryStore,
    MemoryWriteProposal,
    NodeLabel,
)

try:  # package context (pytest collects this as benchmarks.c3_knowledge_web_convergence)
    from .report import BenchmarkReport, Verdict
except ImportError:  # direct-path context (backend/tests/benchmarks on sys.path[0])
    from report import BenchmarkReport, Verdict

# Reuses c3_multimodal.py's shared-entity token for narrative continuity (both
# probes are about the same benchmark's convergence claim) — defined locally,
# not imported, so this file has no dependency on that one.
SHARED_ENTITY = "MarrowgateIndex"
_SCOPE = GraphScope(user_id="c3-kw-benchmark")
_CLAIM_MEMORY_ID = "c3-bench-claim-1"  # the fixed id the doubled store.upsert returns
_DUMMY_VEC: list[float] = [0.1] * 768


class _disposable_graph_db:
    """Self-contained disposable Kuzu db — same pattern as
    c2_repo_intelligence.py's helper (never touches the real dev/prod graph
    db, safe under pytest's own autouse ``_fresh_graph_store`` fixture)."""

    def __enter__(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="clannon-c3-kw-bench-")
        self._prev_env = os.environ.get("VRAKSHA_GRAPH_DB_PATH")
        os.environ["VRAKSHA_GRAPH_DB_PATH"] = str(Path(self._dir) / "graph_db")
        graph_store_mod._db = None
        graph_store_mod._conn = None
        graph_store_mod._schema_ready = False
        return None

    def __exit__(self, *exc_info) -> None:
        graph_store_mod._db = None
        graph_store_mod._conn = None
        graph_store_mod._schema_ready = False
        if self._prev_env is None:
            os.environ.pop("VRAKSHA_GRAPH_DB_PATH", None)
        else:
            os.environ["VRAKSHA_GRAPH_DB_PATH"] = self._prev_env
        shutil.rmtree(self._dir, ignore_errors=True)


async def _real_memory_extractor_path() -> dict:
    """Drive the REAL write_policy -> writer.extract_entities ->
    GraphManager.write() path for one ASSUMPTION-kind memory naming
    SHARED_ENTITY. Only the Qdrant store, the embedder, and the
    entity-extraction LLM call are doubled — the graph write itself is real."""
    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [_DUMMY_VEC for _ in texts]

    def fake_search(tier, user_id, vector, limit) -> list[dict]:
        return []  # always a fresh insert — this probe needs exactly one write

    def fake_upsert(*a, **k) -> str:
        return _CLAIM_MEMORY_ID

    async def fake_extract_entities(content: str) -> writer_mod.ExtractedEntities:
        return writer_mod.ExtractedEntities(
            entities=[writer_mod._ExtractedEntity(name=SHARED_ENTITY, entity_type="concept")],
        )

    with patch.object(embeddings_mod, "embed", fake_embed), \
         patch.object(store_mod, "search", fake_search), \
         patch.object(store_mod, "upsert", fake_upsert), \
         patch.object(writer_mod, "extract_entities", fake_extract_entities):
        persisted = await MemoryManager().record_write_proposals(
            _SCOPE.user_id, "c3-kw-session",
            [MemoryWriteProposal(
                store=MemoryStore.SEMANTIC,
                content=f"{SHARED_ENTITY} coordinates retrieval across the memory tiers.",
                confidence=0.9, kind=MemoryKind.ASSUMPTION,
            )],
        )
    return dict(persisted=persisted)


async def _synthetic_media_path(manager: GraphManager) -> dict:
    """Hand-seed ONE MediaSegment node naming the SAME shared entity —
    SIMULATING the not-yet-built §3.4 media extractor's output. This is NOT
    automatic media ingestion; nothing here parses real audio/video/PDF."""
    segment_key = "c3-bench-media:0-10"
    segment_id = graph_store_mod.node_id(_SCOPE, segment_key)
    entity_canonical = SHARED_ENTITY.strip().lower()
    entity_id = graph_store_mod.node_id(_SCOPE, entity_canonical)

    segment_node = GraphNode(
        node_id=segment_id, label=NodeLabel.MEDIA_SEGMENT, scope=_SCOPE,
        properties={
            "segment_key": segment_key,  # the natural-key property write() mints the id from
            "modality": "audio", "source_media_id": "c3-bench-media",
            "start_ts": 0.0, "end_ts": 10.0,
            "text": f"a synthetic transcript segment mentioning {SHARED_ENTITY}",
        },
    )
    entity_node = GraphNode(
        node_id=entity_id, label=NodeLabel.ENTITY, scope=_SCOPE,
        properties={"canonical_name": entity_canonical, "entity_type": "concept"},
    )
    relates_edge = GraphEdge(
        src_id=entity_id, dst_id=segment_id, label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED,
    )

    write_result = await manager.write(_SCOPE, [segment_node, entity_node], [relates_edge])
    return dict(write=write_result, segment_id=segment_id, entity_id=entity_id)


async def _run_probe() -> dict:
    manager = GraphManager()
    memory_result = await _real_memory_extractor_path()
    media_result = await _synthetic_media_path(manager)

    entity_canonical = SHARED_ENTITY.strip().lower()
    entity_id = graph_store_mod.node_id(_SCOPE, entity_canonical)
    claim_id = graph_store_mod.node_id(_SCOPE, _CLAIM_MEMORY_ID)

    all_entities = await manager.members(_SCOPE, NodeLabel.ENTITY)
    matching_entities = [n for n in all_entities.nodes if n.properties.get("canonical_name") == entity_canonical]
    relates_edges = await manager.edges_of(_SCOPE, entity_id, EdgeLabel.RELATES_TO)

    return dict(
        memory_result=memory_result,
        media_result=media_result,
        matching_entities=matching_entities,
        relates_edges=relates_edges,
        entity_id=entity_id,
        claim_id=claim_id,
    )


def _build_report(probe: dict) -> BenchmarkReport:
    report = BenchmarkReport(
        benchmark_id="C3",
        title="Unified Multi-Modal Representation — knowledge-web convergence (substrate probe)",
        requirement_summary="graph_convergence_mechanism / shared_entities_across_media / media_extractor_pipeline",
    )

    memory_result, media_result = probe["memory_result"], probe["media_result"]
    persisted_ok = len(memory_result["persisted"]) == 1
    media_write_ok = not media_result["write"].degraded and len(media_result["write"].nodes) == 2

    if not persisted_ok or not media_write_ok:
        report.add_requirement(
            "graph_convergence_mechanism", "Converge shared entities across origin types", Verdict.FAIL,
            f"setup did not hold: memory-extractor write persisted_ok={persisted_ok}, "
            f"synthetic media-segment write media_write_ok={media_write_ok}.",
        )
        return report

    entity_id, claim_id, segment_id = probe["entity_id"], probe["claim_id"], media_result["segment_id"]
    matching_entities = probe["matching_entities"]
    relates_edges = probe["relates_edges"].edges
    connected_ids = {(e.dst_id if e.src_id == entity_id else e.src_id) for e in relates_edges}

    entity_count_ok = len(matching_entities) == 1
    convergence_ok = claim_id in connected_ids and segment_id in connected_ids

    # --- graph_convergence_mechanism: the real, substrate-specific claim ---
    if entity_count_ok and convergence_ok:
        report.add_requirement(
            "graph_convergence_mechanism", "Converge shared entities across origin types", Verdict.PASS,
            f"a CLAIM written through the REAL memory extractor and a hand-seeded "
            f"MediaSegment (simulating §3.4) both named '{SHARED_ENTITY}' and "
            f"converged onto exactly ONE ENTITY node (canonical_name convergence, "
            f"§1.1), each linked to it via its own RELATES_TO edge — read back "
            f"through the real GraphPort (members()/edges_of()), not asserted.",
            (f"entity rows matching canonical_name={entity_canonical_note(SHARED_ENTITY)}: {len(matching_entities)}",
             f"RELATES_TO({entity_id}) connects to: {sorted(connected_ids)}",
             f"claim_id={claim_id} in connections: {claim_id in connected_ids}",
             f"segment_id={segment_id} in connections: {segment_id in connected_ids}"),
        )
    else:
        report.add_requirement(
            "graph_convergence_mechanism", "Converge shared entities across origin types", Verdict.FAIL,
            f"convergence did not hold: entity_count_ok={entity_count_ok} "
            f"({len(matching_entities)} matching entity rows, expected 1), "
            f"convergence_ok={convergence_ok} (connected={sorted(connected_ids)}, "
            f"expected both claim_id={claim_id} and segment_id={segment_id}).",
        )

    # --- shared_entities_across_media: PARTIAL — one side is hand-seeded ---
    report.add_requirement(
        "shared_entities_across_media", "Create shared entities across media", Verdict.PARTIAL,
        "the convergence mechanism itself is real and proven above, but ONE of "
        "the two converging origins (the MediaSegment) is hand-seeded here, not "
        "produced by a real media-ingestion pipeline — §3.4 (the automatic "
        "PDF/audio/video -> MediaSegment extractor) does not exist. This is "
        "genuinely closer to the benchmark's real claim than string-survival "
        "alone (c3_multimodal.py), but it is not automatic cross-media entity "
        "creation end-to-end, so PARTIAL, not PASS.",
    )

    # --- media_extractor_pipeline: honest, explicit NOT-YET ---
    report.add_requirement(
        "media_extractor_pipeline", "Automatically extract entities from real media", Verdict.NOT_YET,
        "no PDF/audio/video/image -> MediaSegment extraction pipeline exists "
        "(§3.4 of the ratified knowledge-web design). This is a cross-tree "
        "dependency (the media pipeline's build, not core/memory/'s) — this "
        "harness hand-seeds ONE MediaSegment row to simulate that extractor's "
        "eventual output and does not build the extractor itself.",
    )

    report.add_case("memory_extractor:claim", "written", f"id={claim_id}")
    report.add_case("synthetic:media_segment", "hand-seeded (simulates §3.4)", f"id={segment_id}")
    report.add_case("entity:convergence", "recalled" if entity_count_ok else "DIVERGED",
                     f"{len(matching_entities)} entity row(s) for '{SHARED_ENTITY}'")

    report.add_note(
        f"scenario: '{SHARED_ENTITY}' is asserted by two independently-written "
        "graph paths — a real memory-extractor-fed CLAIM and a hand-seeded "
        "MediaSegment — to prove the convergence RULE (§1.1: identity = "
        "normalized canonical_name) holds across origin types, not just within "
        "one write.")
    report.add_note(
        "hermetic seams: the Qdrant store, the embedder, and the entity-"
        "extraction LLM call are doubled (deterministic, no network/model/paid "
        "key) — the SAME discipline as every other benchmark harness. The graph "
        "write itself (GraphManager -> Kuzu, a disposable per-run db) is real.")
    report.add_note(
        "companion to c3_multimodal.py (the ingestion-precondition proof), not "
        "a replacement — that file's own certified requirements/tests are "
        "untouched. Not yet wired into scripts/benchmarks/run_all.py's fixed "
        "C3 slot; run standalone.")
    report.add_note("serves Critical Benchmark 3 (Unified Multi-Modal Representation).")

    return report


def entity_canonical_note(name: str) -> str:
    """Small helper so the evidence line shows the exact normalized form
    (whitespace-collapsed, lowercased — write_policy._normalize_entity_name's
    own rule) without importing a private function across files."""
    return " ".join(name.split()).lower()


def run() -> BenchmarkReport:
    """Entry point for standalone use (not yet wired into run_all.py)."""
    with _disposable_graph_db():
        probe = asyncio.run(_run_probe())
    return _build_report(probe)


# ---------------------------------------------------------------------------
# Pytest entry points
# ---------------------------------------------------------------------------

def test_graph_convergence_mechanism_passes_across_origin_types():
    report = run()
    print("\n" + report.render())
    by_key = {r.key: r for r in report.requirements}
    assert by_key["graph_convergence_mechanism"].verdict is Verdict.PASS, "\n" + report.render()


def test_shared_entities_across_media_is_honestly_partial_not_pass():
    """LAW 6: a hand-seeded MediaSegment must never score PASS on a
    media-worded requirement, no matter how well the graph mechanism works."""
    report = run()
    by_key = {r.key: r for r in report.requirements}
    assert by_key["shared_entities_across_media"].verdict is Verdict.PARTIAL, "\n" + report.render()


def test_media_extractor_pipeline_is_honestly_not_yet():
    report = run()
    by_key = {r.key: r for r in report.requirements}
    assert by_key["media_extractor_pipeline"].verdict is Verdict.NOT_YET, "\n" + report.render()


def test_overall_verdict_is_partial_not_a_fabricated_pass():
    report = run()
    assert not report.has_failure(), "\n" + report.render()
    assert report.overall() is Verdict.PARTIAL, "\n" + report.render()


def test_report_renders_structured_block(capsys):
    report = run()
    print(report.render())
    captured = capsys.readouterr().out
    assert "BENCHMARK C3" in captured
    assert "OVERALL:" in captured
    for key in ("graph_convergence_mechanism", "shared_entities_across_media", "media_extractor_pipeline"):
        assert key in captured
    assert SHARED_ENTITY in captured


if __name__ == "__main__":
    print(run().render())
