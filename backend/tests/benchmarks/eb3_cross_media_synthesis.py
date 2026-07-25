"""
Exceptional Benchmark 3 — Cross-Media Knowledge Synthesis

Per the ratified knowledge-web design (§5): "Prove a CONTRADICTS or RELATES_TO
edge spanning a MEDIA_SEGMENT and a memory-derived CLAIM (e.g. a transcript
says X, a stored assumption says not-X) — the genuinely cross-modal synthesis
EB3 asks for, distinct from CB3's same-entity convergence."

A real, honest finding from actually building this (not assumed, verified
against `core/memory/graph_schema.py`'s DDL and the design's own §1.4 edge
table): **no edge table has a direct Claim<->MediaSegment pair.**
`Contradicts` is `FROM Claim TO Claim` only (the design's own table says so:
"CONTRADICTS | CLAIM<->CLAIM (same ENTITY)"). `RelatesTo` is
Entity-centric — every pair has `Entity` on one side (`FROM Entity TO Entity,
Fact, Claim, MediaSegment`); there is no `FROM Claim TO MediaSegment` (or
reverse) pair in either table. A literal direct edge between a CLAIM and a
MEDIA_SEGMENT is therefore **not representable in the schema as ratified and
built** — not merely gated on the not-yet-built media extractor (§3.4), a
DIFFERENT and more specific gap than CB3's. This harness proves what IS
real (an ENTITY-mediated cross-modal link, one RELATES_TO hop each way — the
same convergence mechanism `c3_knowledge_web_convergence.py` proves, reused
here because it IS the honest cross-modal reachability this substrate offers
today) and scores the literal direct-edge ask + the semantic contradiction
judgment (comparing a transcript's actual content against a claim's) as
NOT-YET, naming exactly why. Flagged to backend as a schema-completeness
finding (proposals/to-backend/), not silently patched — adding a new
heterogeneous pair to an already-ratified table is a schema decision, not a
benchmark-harness call.

Hermetic seams: same discipline as `c3_knowledge_web_convergence.py` — the
Qdrant store, embedder, and entity-extraction LLM call are doubled
(deterministic, no network/model/paid key); the MediaSegment is hand-seeded
(simulates §3.4's not-yet-built output, labeled everywhere); the graph write
itself (GraphManager -> a disposable per-run Kuzu db) is real.

Run:
    cd backend && .venv/bin/python -m pytest tests/benchmarks/eb3_cross_media_synthesis.py -v
    PYTHONPATH=tests python -m benchmarks.eb3_cross_media_synthesis   # prints report

``run()`` returns the ``BenchmarkReport`` for the consolidated scoreboard —
wired into ``scripts/benchmarks/run_all.py``'s E3 slot (previously a
hardcoded "no harness" placeholder).
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

try:  # package context (pytest collects this as benchmarks.eb3_cross_media_synthesis)
    from .report import BenchmarkReport, Verdict
except ImportError:  # direct-path context (backend/tests/benchmarks on sys.path[0])
    from report import BenchmarkReport, Verdict

# A distinctive entity both "modalities" name, so the transcript and the claim
# are unambiguously about the same real-world thing (not a topical coincidence).
SHARED_ENTITY = "QuorumLedger"
_SCOPE = GraphScope(user_id="eb3-benchmark")
_CLAIM_MEMORY_ID = "eb3-bench-claim-1"
_DUMMY_VEC: list[float] = [0.1] * 768

# The contradiction narrative the design's own example uses: "a transcript
# says X, a stored assumption says not-X."
_CLAIM_CONTENT = f"{SHARED_ENTITY} is deployed to production."
_TRANSCRIPT_TEXT = f"{SHARED_ENTITY} was rolled back and is NOT in production."


class _disposable_graph_db:
    """Self-contained disposable Kuzu db — same pattern as the other graph
    benchmark harnesses (c2/c3 companion probe)."""

    def __enter__(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="clannon-eb3-bench-")
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
    """The REAL write_policy -> writer.extract_entities -> GraphManager.write()
    path for one ASSUMPTION-kind memory asserting X about SHARED_ENTITY. Only
    the Qdrant store, embedder, and entity-extraction LLM call are doubled."""
    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [_DUMMY_VEC for _ in texts]

    def fake_search(tier, user_id, vector, limit) -> list[dict]:
        return []

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
            _SCOPE.user_id, "eb3-session",
            [MemoryWriteProposal(
                store=MemoryStore.SEMANTIC, content=_CLAIM_CONTENT,
                confidence=0.9, kind=MemoryKind.ASSUMPTION,
            )],
        )
    return dict(persisted=persisted)


async def _synthetic_media_path(manager: GraphManager) -> dict:
    """Hand-seed ONE MediaSegment asserting the OPPOSITE of the claim above —
    SIMULATING §3.4's not-yet-built extractor. Not real media ingestion."""
    segment_key = "eb3-bench-media:0-8"
    segment_id = graph_store_mod.node_id(_SCOPE, segment_key)
    entity_canonical = SHARED_ENTITY.strip().lower()
    entity_id = graph_store_mod.node_id(_SCOPE, entity_canonical)

    segment_node = GraphNode(
        node_id=segment_id, label=NodeLabel.MEDIA_SEGMENT, scope=_SCOPE,
        properties={
            "segment_key": segment_key,
            "modality": "audio", "source_media_id": "eb3-bench-media",
            "start_ts": 0.0, "end_ts": 8.0, "text": _TRANSCRIPT_TEXT,
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


async def _probe_direct_edge_support(manager: GraphManager, claim_id: str, segment_id: str) -> tuple[bool, str]:
    """EMPIRICAL check, not static inspection: `knowledge_store.py`'s
    `_TYPED_EDGE_TABLES` registry only lists which tables an edge kind
    RESOLVES against (RelatesTo's candidates are `(Entity, Fact, Claim,
    MediaSegment)` as a heterogeneous SET) — it does NOT record the actual
    FROM/TO pairs the underlying Kuzu `CREATE REL TABLE` enforces (verified:
    every RelatesTo pair has Entity on one side; Claim->MediaSegment is not
    among them). A static registry check false-positives on this. So: attempt
    a REAL direct Claim->MediaSegment RELATES_TO write through the port and
    observe whether it actually applied — the same 'verify against real
    Kuzu, don't assume' discipline every other harness in this suite follows."""
    direct_edge = GraphEdge(src_id=claim_id, dst_id=segment_id, label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED)
    write_result = await manager.write(_SCOPE, [], [direct_edge])
    landed = any(e.src_id == claim_id and e.dst_id == segment_id for e in write_result.edges)
    if landed:
        return True, "a direct Claim->MediaSegment RELATES_TO edge was written and applied"
    return False, (
        "a direct Claim->MediaSegment RELATES_TO write was attempted through the real port and "
        "did NOT apply — RelatesTo's real Kuzu FROM/TO pairs are all Entity-centric "
        "(Entity->{Entity,Fact,Claim,MediaSegment}); Claim->MediaSegment is not among them, "
        "matching the design's own §1.4 table ('CONTRADICTS | CLAIM<->CLAIM'; RelatesTo listed "
        "only as Entity<->{Fact,Claim,MediaSegment,Entity})"
    )


async def _run_probe() -> dict:
    manager = GraphManager()
    memory_result = await _real_memory_extractor_path()
    media_result = await _synthetic_media_path(manager)

    entity_canonical = SHARED_ENTITY.strip().lower()
    entity_id = graph_store_mod.node_id(_SCOPE, entity_canonical)
    claim_id = graph_store_mod.node_id(_SCOPE, _CLAIM_MEMORY_ID)
    segment_id = media_result["segment_id"]
    relates_edges = await manager.edges_of(_SCOPE, entity_id, EdgeLabel.RELATES_TO)
    schema_ok, schema_reason = await _probe_direct_edge_support(manager, claim_id, segment_id)

    return dict(
        memory_result=memory_result, media_result=media_result,
        entity_id=entity_id, claim_id=claim_id, relates_edges=relates_edges,
        schema_ok=schema_ok, schema_reason=schema_reason,
    )


def _build_report(probe: dict) -> BenchmarkReport:
    report = BenchmarkReport(
        benchmark_id="E3", title="Cross-Media Knowledge Synthesis",
        requirement_summary="entity_mediated_cross_modal_link / direct_cross_modal_edge / "
                             "cross_modal_contradiction_semantics",
    )

    memory_result, media_result = probe["memory_result"], probe["media_result"]
    persisted_ok = len(memory_result["persisted"]) == 1
    media_write_ok = not media_result["write"].degraded and len(media_result["write"].nodes) == 2

    if not persisted_ok or not media_write_ok:
        report.add_requirement(
            "entity_mediated_cross_modal_link", "Link a CLAIM and a MEDIA_SEGMENT through the graph",
            Verdict.FAIL,
            f"setup did not hold: persisted_ok={persisted_ok}, media_write_ok={media_write_ok}.",
        )
        return report

    entity_id, claim_id = probe["entity_id"], probe["claim_id"]
    segment_id = media_result["segment_id"]
    connected_ids = {(e.dst_id if e.src_id == entity_id else e.src_id) for e in probe["relates_edges"].edges}
    link_ok = claim_id in connected_ids and segment_id in connected_ids

    # --- entity_mediated_cross_modal_link: the real, substrate-provable claim ---
    if link_ok:
        report.add_requirement(
            "entity_mediated_cross_modal_link", "Link a CLAIM and a MEDIA_SEGMENT through the graph",
            Verdict.PASS,
            f"a memory-extractor-fed CLAIM asserting '{_CLAIM_CONTENT}' and a hand-seeded "
            f"MediaSegment transcript asserting the OPPOSITE ('{_TRANSCRIPT_TEXT}') both "
            f"RELATES_TO the same ENTITY node — genuinely reachable from one to the other "
            f"through the graph (one hop each way), read back through the real GraphPort.",
            (f"RELATES_TO({entity_id}) connects to: {sorted(connected_ids)}",
             f"claim_id in link: {claim_id in connected_ids}",
             f"segment_id in link: {segment_id in connected_ids}"),
        )
    else:
        report.add_requirement(
            "entity_mediated_cross_modal_link", "Link a CLAIM and a MEDIA_SEGMENT through the graph",
            Verdict.FAIL,
            f"the entity-mediated link did not hold: connected={sorted(connected_ids)}, "
            f"expected both claim_id={claim_id} and segment_id={segment_id}.",
        )

    # --- direct_cross_modal_edge: a genuine, verified schema gap, not a defect ---
    schema_ok, schema_reason = probe["schema_ok"], probe["schema_reason"]
    report.add_requirement(
        "direct_cross_modal_edge",
        "A single CONTRADICTS/RELATES_TO edge spanning CLAIM<->MEDIA_SEGMENT directly",
        Verdict.PASS if schema_ok else Verdict.NOT_YET,
        (f"the schema DOES register an edge table pairing Claim with MediaSegment: {schema_reason}."
         if schema_ok else
         f"VERIFIED GAP (not assumed — checked knowledge_store.py's own edge-table registry): "
         f"{schema_reason}. Contradicts is Claim-to-Claim only (matches the design's own §1.4 "
         "table: 'CONTRADICTS | CLAIM<->CLAIM'); RelatesTo is Entity-centric (every pair has "
         "Entity on one side). A literal DIRECT edge between a CLAIM and a MEDIA_SEGMENT is not "
         "representable in the schema as ratified and built — this is a schema-completeness gap, "
         "flagged to backend, not silently patched here (adding a heterogeneous pair to an "
         "already-ratified table is a schema decision, not a benchmark-harness call)."),
    )

    # --- cross_modal_contradiction_semantics: honest, explicit NOT-YET ---
    report.add_requirement(
        "cross_modal_contradiction_semantics",
        "Judge whether a transcript's content actually contradicts a claim's content",
        Verdict.NOT_YET,
        "no contradiction judge compares MediaSegment text against Claim content today — "
        "`writer.judge_contradiction`/`write_policy._judge_contradictions` (§3.2, shipped this "
        "session) only ever compare CLAIM against CLAIM (matching Contradicts' Claim-only "
        "schema above). A real cross-modal semantic judgment needs BOTH the schema gap closed "
        "AND a judge extended (or a new one) to read MediaSegment text — neither built here; "
        "this harness only proves the entity-mediated graph reachability, not a content-level "
        "contradiction verdict.",
    )

    report.add_case("memory_extractor:claim", "written", f"content='{_CLAIM_CONTENT}'")
    report.add_case("synthetic:media_segment", "hand-seeded (simulates §3.4)", f"text='{_TRANSCRIPT_TEXT}'")
    report.add_case("graph:entity_mediated_link", "recalled" if link_ok else "DIVERGED",
                     f"both endpoints connect to entity={entity_id}")

    report.add_note(
        f"narrative: the claim asserts '{_CLAIM_CONTENT}', the synthetic transcript asserts "
        f"the OPPOSITE — the design's own example shape ('a transcript says X, a stored "
        "assumption says not-X') — but this harness does NOT claim the system recognized the "
        "contradiction; only that both are graph-reachable from a shared entity.")
    report.add_note(
        "hermetic seams: Qdrant store, embedder, and entity-extraction LLM call doubled "
        "(deterministic, no network/model/paid key). The graph write is real (GraphManager -> "
        "a disposable per-run Kuzu db).")
    report.add_note(
        "distinct from c3_knowledge_web_convergence.py: that probe proves ENTITY convergence "
        "(one shared node); this one specifically targets the DIRECT cross-item edge EB3's own "
        "wording asks for, and is the harness that surfaced the schema gap above.")
    report.add_note("serves Exceptional Benchmark 3 (Cross-Media Knowledge Synthesis).")

    return report


def run() -> BenchmarkReport:
    with _disposable_graph_db():
        probe = asyncio.run(_run_probe())
    return _build_report(probe)


# ---------------------------------------------------------------------------
# Pytest entry points
# ---------------------------------------------------------------------------

def test_entity_mediated_cross_modal_link_passes():
    report = run()
    print("\n" + report.render())
    by_key = {r.key: r for r in report.requirements}
    assert by_key["entity_mediated_cross_modal_link"].verdict is Verdict.PASS, "\n" + report.render()


def test_direct_cross_modal_edge_is_an_honest_schema_gap_not_yet():
    """LAW 6: don't fake a pass — the schema genuinely has no Claim<->MediaSegment
    pair today (verified against knowledge_store.py's own registry, not assumed)."""
    report = run()
    by_key = {r.key: r for r in report.requirements}
    assert by_key["direct_cross_modal_edge"].verdict is Verdict.NOT_YET, "\n" + report.render()


def test_cross_modal_contradiction_semantics_is_honestly_not_yet():
    report = run()
    by_key = {r.key: r for r in report.requirements}
    assert by_key["cross_modal_contradiction_semantics"].verdict is Verdict.NOT_YET, "\n" + report.render()


def test_overall_verdict_is_not_yet_not_a_fabricated_pass():
    report = run()
    assert not report.has_failure(), "\n" + report.render()
    assert report.overall() is Verdict.NOT_YET, "\n" + report.render()


def test_report_renders_structured_block(capsys):
    report = run()
    print(report.render())
    captured = capsys.readouterr().out
    assert "BENCHMARK E3" in captured
    assert "OVERALL:" in captured
    for key in ("entity_mediated_cross_modal_link", "direct_cross_modal_edge",
                "cross_modal_contradiction_semantics"):
        assert key in captured
    assert SHARED_ENTITY in captured


if __name__ == "__main__":
    print(run().render())
