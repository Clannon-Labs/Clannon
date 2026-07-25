"""
Critical Benchmark 2 — Large Repository Understanding (thin slice)

Probes whether the memory layer can answer structural questions about a repo
too large to fit in one prompt — "what does X depend on," "what breaks if X
is removed" — by querying a pre-built graph index, never by re-reading source
at query time.

Benchmark scenario (docs/benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md,
Critical Benchmark 2 / docs/benchmarks/V1_GAP_ANALYSIS.md §CB2): the full
benchmark (five graph types: file/dependency/architectural/decision/ownership,
docs/decisions/proposed/0008-repository-intelligence.md) blocks on the
graph-web/batch architecture (owner-gated, parked). This harness is the
ratified THIN SLICE (proposals/archive/to-backend/
2026-07-05_cb2-thin-slice-benchmark-spec.md): the code-only static import/
dependency graph, already built and unit-tested (GraphPort/GraphManager/
graph_store.py's Kuzu wrapper/graph_extract.py's ast extractor — 53 tests
across memory_graph_manager.py/memory_graph_store.py/memory_graph_extract.py).
No new mechanism here, purely the formal run() -> BenchmarkReport harness
(the C1/C3/C4/E2 convention) scoring CB2's own five pass requirements against
Clannon's own real backend/ tree — CB2's "Examples" list names Clannon first,
and a toy fixture would undersell the actual point (a repo bigger than one
prompt).

Boundary (stated once, applies throughout): this graph substrate returns
structured query RESULTS (file paths, edge origins) — producing natural-
language architectural EXPLANATIONS ("here's why X depends on Y") is an LLM
synthesis step the orchestrator performs over those results, not the graph
substrate's job. Same line e2_project_continuity.py draws between hydration
and narrative synthesis. Scored honestly as NOT-YET, not hidden.

Explicitly out of scope (the gap analysis's own "thin slice, not a graph-web"
framing): behavioral/data-flow questions ("how does auth propagate"), the
architectural-boundary narrative ("what boundaries exist"), and the other
four graph types (file/architectural/decision/ownership) beyond dependency.

Robustness: repo file/edge counts drift under ordinary feature work (this
session alone added ~15 files since the last count). Exact-count assertions
would make routine work look like a regression, so this harness asserts
FLOORS (well below the current real count) plus a small set of structurally
durable facts unlikely to ever change (the single-write-door dependency
itself: manager.py depends_on store.py) — the same tension C4 solves with
its _MIN_ADRS floor rather than an exact ADR count.

Cross-batch knowledge (added 2026-07-25, per the ratified knowledge-web design's
§5 "CB2 (full)" commitment — proposals/archive/to-backend/
2026-07-06_knowledge-web-design-cb2-cb3-eb3.md): once the memory extractor
(§3.1) landed, the substrate can prove the OTHER half of "full cross-batch
knowledge" that doesn't need the code-symbol tier (§3.3, still gated on
orchestration's extractor, honestly scored NOT-YET below) — that separate
batches' output lands in ONE shared knowledge graph, each piece still
traceable back to the TASK that produced it, via `DERIVED_FROM` +
`edges_of()`. Two synthetic TASK nodes (standing in for two different
batches), each with its own FACT node `DERIVED_FROM` it — proven with the
real `GraphManager.write()`/`edges_of()` port, not the internal store
functions `tests/memory_knowledge_store.py` already covers at the unit level
(this is the port-level, benchmark-shaped proof).

Run:
    cd backend && .venv/bin/python -m pytest tests/benchmarks/c2_repo_intelligence.py -v
    PYTHONPATH=tests python -m benchmarks.c2_repo_intelligence   # prints report

run() returns the BenchmarkReport for the consolidated scoreboard harness.
"""
from __future__ import annotations

import ast
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import core.memory.graph_store as graph_store_mod
from core.memory.graph_manager import GraphManager
from foundation import EdgeLabel, EdgeOrigin, GraphEdge, GraphNode, GraphScope, NodeLabel

try:  # package context (pytest collects this as benchmarks.c2_repo_intelligence)
    from .report import BenchmarkReport, Verdict
except ImportError:  # direct-path context (backend/tests/benchmarks on sys.path[0])
    from report import BenchmarkReport, Verdict

# tests/benchmarks/c2_repo_intelligence.py -> tests/ -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_SCOPE = GraphScope(user_id="c2-benchmark", repo_id="clannon-self")

# Durable structural facts, reverified fresh against the real tree the day this
# harness was written (277 files, 889 edges) — floors set well below that so
# ordinary file churn doesn't fail this, only a genuine "extractor stopped
# working" regression would.
_MIN_FILES = 200
_MIN_EDGES = 600
_MIN_BREAKS_IF_STORE_REMOVED = 50
_MIN_FOUNDATION_DEPENDENTS = 100

_MANAGER = "core/memory/manager.py"
_STORE = "core/memory/store.py"
_FOUNDATION_INIT = "foundation/__init__.py"
# The single-write-door invariant itself, expressed as a graph edge — a
# foundational, deliberate relationship (§V.20) unlikely to ever break under
# routine work, unlike an exact file/edge count.
_EXPECTED_DIRECT_DEPS_OF_MANAGER = {
    # Post-013ea90 (manager.py split into thin door + hydration/write_policy/
    # tiers): manager.py no longer imports embeddings.py directly — that's
    # write_policy.py's/hydration.py's job now. Kept as a durable subset of
    # manager.py's real direct imports (not the full set), same spirit as
    # before: pin a few structurally meaningful facts, not an exact count.
    "core/memory/__init__.py", "core/memory/write_policy.py",
    "core/memory/store.py", "core/memory/writer.py", "foundation/__init__.py",
}


class _disposable_graph_db:
    """Self-contained disposable Kuzu db, same pattern as
    scripts/cb2_repo_intelligence_demo.py: never touches the real dev/prod
    graph db, safe to call repeatedly (run_all.py invokes run() standalone,
    outside any pytest fixture). Also safe to nest under pytest's own
    autouse _fresh_graph_store (tests/conftest.py) — this just gives an
    even-fresher disposable path and restores the outer one on exit."""

    def __enter__(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="clannon-c2-bench-")
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


_CROSS_BATCH_MISSION = "m-cb2-bench"
_CROSS_BATCH_TASKS = ("batch-a-task", "batch-b-task")


async def _run_cross_batch_probe(manager: GraphManager) -> dict:
    """The 'full cross-batch knowledge' half of CB2 (full) that does NOT need
    the code-symbol tier: two synthetic TASK nodes stand in for two different
    batches, each producing its own FACT node `DERIVED_FROM` it. Proves
    separate batches' output lands in ONE shared knowledge graph, each piece
    still traceable back to its origin — through the real `GraphPort.write()`/
    `edges_of()`, not the internal store functions."""
    task_ids = [graph_store_mod.node_id(_SCOPE, t) for t in _CROSS_BATCH_TASKS]
    task_nodes = [
        GraphNode(
            node_id=tid, label=NodeLabel.TASK, scope=_SCOPE,
            properties={"task_id": t, "mission_id": _CROSS_BATCH_MISSION,
                        "summary": f"{t} did some work", "status": "done", "evidence": "",
                        "updated_at": 1.0},
        )
        for tid, t in zip(task_ids, _CROSS_BATCH_TASKS)
    ]
    fact_ids = [graph_store_mod.node_id(_SCOPE, f"cb2-bench-fact-{i}") for i in range(len(_CROSS_BATCH_TASKS))]
    fact_nodes = [
        GraphNode(
            node_id=fid, label=NodeLabel.FACT, scope=_SCOPE,
            properties={"content": f"fact produced by {t}", "vector_id": f"cb2-bench-fact-{i}"},
        )
        for i, (fid, t) in enumerate(zip(fact_ids, _CROSS_BATCH_TASKS))
    ]
    derived_from_edges = [
        GraphEdge(src_id=fid, dst_id=tid, label=EdgeLabel.DERIVED_FROM, origin=EdgeOrigin.INFERRED)
        for fid, tid in zip(fact_ids, task_ids)
    ]

    write_result = await manager.write(_SCOPE, task_nodes + fact_nodes, derived_from_edges)
    edges_of_task = [await manager.edges_of(_SCOPE, tid, EdgeLabel.DERIVED_FROM) for tid in task_ids]

    return dict(
        write=write_result,
        task_ids=task_ids,
        fact_ids=fact_ids,
        edges_of_task=edges_of_task,
    )


async def _run_probe() -> dict:
    """Build the real code-import graph over Clannon's own backend/ tree, run
    the CB2-shaped queries through the port, and empirically pin the headline
    claim (queries never re-read source) by patching Path.read_text/ast.parse
    AFTER the build and asserting neither fires during any query below."""
    manager = GraphManager()
    real_read_text = Path.read_text
    real_ast_parse = ast.parse

    build_touched: list[str] = []

    def _counting_read_text(self, *a, **kw):
        build_touched.append(str(self))
        return real_read_text(self, *a, **kw)

    with patch.object(Path, "read_text", _counting_read_text):
        build = await manager.build_code_graph(_SCOPE, _BACKEND_ROOT)

    # Sanity check on the probe mechanism itself, not a scored requirement: if
    # this ever trips, the empirical pin below would be vacuously true (never
    # actually exercising the patched path), which would be worse than not
    # having the pin at all.
    assert build_touched, "build_code_graph should read real files — probe mechanism is broken"

    query_touched: list[str] = []

    def _tripwire_read_text(self, *a, **kw):
        query_touched.append(str(self))
        return real_read_text(self, *a, **kw)

    def _tripwire_ast_parse(*a, **kw):
        query_touched.append("ast.parse")
        return real_ast_parse(*a, **kw)

    node_id = graph_store_mod.node_id
    with patch.object(Path, "read_text", _tripwire_read_text), patch.object(ast, "parse", _tripwire_ast_parse):
        depends_on_manager = await manager.depends_on(_SCOPE, node_id(_SCOPE, _MANAGER))
        breaks_if_store_removed = await manager.breaks_if_removed(_SCOPE, node_id(_SCOPE, _STORE))
        foundation_dependents_1hop = await manager.dependents_of(_SCOPE, node_id(_SCOPE, _FOUNDATION_INIT), max_hops=1)
        foundation_dependents_20hop = await manager.dependents_of(_SCOPE, node_id(_SCOPE, _FOUNDATION_INIT), max_hops=20)

    cross_batch = await _run_cross_batch_probe(manager)

    return dict(
        build=build,
        depends_on_manager={n.properties["path"] for n in depends_on_manager.nodes},
        breaks_if_store_removed={n.properties["path"] for n in breaks_if_store_removed.nodes},
        foundation_dependents_1hop={n.properties["path"] for n in foundation_dependents_1hop.nodes},
        foundation_dependents_20hop={n.properties["path"] for n in foundation_dependents_20hop.nodes},
        query_reread_calls=query_touched,
        cross_batch=cross_batch,
    )


def _build_report(probe: dict) -> BenchmarkReport:
    report = BenchmarkReport(
        benchmark_id="C2", title="Large Repository Understanding (thin slice)",
        requirement_summary="navigate / trace_dependencies / follow_relationships / "
                             "cross_batch_knowledge / architectural_explanations / "
                             "avoid_single_prompt",
    )

    build = probe["build"]
    deps = probe["depends_on_manager"]
    breaks = probe["breaks_if_store_removed"]
    f1 = probe["foundation_dependents_1hop"]
    f20 = probe["foundation_dependents_20hop"]

    if build.degraded:
        report.add_requirement(
            "build", "Build the code-import graph", Verdict.FAIL,
            f"build_code_graph degraded: {build.notes}")
        return report

    # --- navigate: the extracted node set represents the real file tree ---
    report.add_requirement(
        "navigate", "Navigate repository structure", Verdict.PASS,
        f"ast-based extraction over the real backend/ tree: {build.notes} "
        f"(floor: >= {_MIN_FILES} files, pinned separately in test_probe_floor_counts_hold).",
    )

    # --- trace_dependencies: depends_on returns the correct, durable direct set ---
    trace_ok = _EXPECTED_DIRECT_DEPS_OF_MANAGER <= deps
    report.add_requirement(
        "trace_dependencies", "Trace dependencies", Verdict.PASS if trace_ok else Verdict.FAIL,
        (f"depends_on({_MANAGER}) returns the correct direct-import set through the port."
         if trace_ok else
         f"depends_on({_MANAGER}) is missing an expected direct import: "
         f"expected {_EXPECTED_DIRECT_DEPS_OF_MANAGER}, got {deps}."),
        (f"depends_on({_MANAGER}) = {sorted(deps)}",),
    )

    # --- follow_relationships: multi-hop transitive closure genuinely composes ---
    breaks_floor_ok = len(breaks) >= _MIN_BREAKS_IF_STORE_REMOVED and _MANAGER in breaks
    superset_ok = f20 > f1 and len(f20) >= _MIN_FOUNDATION_DEPENDENTS
    if breaks_floor_ok and superset_ok:
        report.add_requirement(
            "follow_relationships", "Follow relationships across files", Verdict.PASS,
            f"breaks_if_removed({_STORE}) transitively includes {_MANAGER} among "
            f"{len(breaks)} files (floor {_MIN_BREAKS_IF_STORE_REMOVED}); "
            f"dependents_of({_FOUNDATION_INIT}, max_hops=20) is a strict superset of "
            "max_hops=1 — multi-hop traversal genuinely composes, not just direct edges.",
            (f"breaks_if_removed({_STORE}) = {len(breaks)} files",
             f"dependents_of({_FOUNDATION_INIT}, hops=1) = {len(f1)}, "
             f"(hops=20) = {len(f20)}"),
        )
    else:
        report.add_requirement(
            "follow_relationships", "Follow relationships across files", Verdict.FAIL,
            f"multi-hop composition did not hold: breaks_floor_ok={breaks_floor_ok}, "
            f"superset_ok={superset_ok} (breaks={len(breaks)}, f1={len(f1)}, f20={len(f20)}).",
        )

    # --- cross_batch_knowledge: separate batches' output lands in ONE shared
    # graph, each piece still traceable to its origin TASK (§5's "CB2 (full)"
    # cross-batch claim — the half that does NOT need the symbol tier) ---
    cb = probe["cross_batch"]
    cb_write, cb_task_ids, cb_fact_ids, cb_edges_of = (
        cb["write"], cb["task_ids"], cb["fact_ids"], cb["edges_of_task"])
    write_ok = not cb_write.degraded and len(cb_write.nodes) == 4 and len(cb_write.edges) == 2
    traceable_ok = all(
        len(edges.edges) == 1
        and edges.edges[0].src_id == fid
        and edges.edges[0].dst_id == tid
        for edges, fid, tid in zip(cb_edges_of, cb_fact_ids, cb_task_ids)
    )
    if write_ok and traceable_ok:
        report.add_requirement(
            "cross_batch_knowledge", "Hold cross-batch knowledge in one shared graph", Verdict.PASS,
            "two synthetic TASK nodes (standing in for two different batches) each "
            "got their own FACT node DERIVED_FROM it, written through the same "
            "GraphManager.write() call — both land in the SAME shared graph, and "
            "each is still traceable back to its own origin TASK via edges_of(). "
            "This is the port-level proof of the file-level-independent half of "
            "'full cross-batch knowledge'; the code-symbol-tier half (§3.3, "
            "function/struct-level nodes) is separately scored NOT-YET below.",
            (f"task_ids = {cb_task_ids}", f"fact_ids = {cb_fact_ids}",
             f"DERIVED_FROM(task_a) -> {[e.src_id for e in cb_edges_of[0].edges]}",
             f"DERIVED_FROM(task_b) -> {[e.src_id for e in cb_edges_of[1].edges]}"),
        )
    else:
        report.add_requirement(
            "cross_batch_knowledge", "Hold cross-batch knowledge in one shared graph", Verdict.FAIL,
            f"cross-batch write/read-back did not hold: write_ok={write_ok} "
            f"(degraded={cb_write.degraded}, nodes={len(cb_write.nodes)}, "
            f"edges={len(cb_write.edges)}), traceable_ok={traceable_ok}.",
        )

    # --- architectural_explanations: honest, explicit NOT-YET ---
    report.add_requirement(
        "architectural_explanations", "Provide architectural explanations", Verdict.NOT_YET,
        "the graph substrate returns structured query results (file paths, edge "
        "origins), not natural-language explanations. Producing prose ('here's why "
        "X depends on Y') is an LLM synthesis step over these results — the "
        "orchestrator's job, not the graph substrate's. Not implemented here by "
        "design, not a defect.",
    )

    # --- avoid_single_prompt: structural (by construction) + empirical pin ---
    reread_calls = probe["query_reread_calls"]
    if not reread_calls:
        report.add_requirement(
            "avoid_single_prompt", "Avoid loading repository into a single prompt", Verdict.PASS,
            "queries only ever touch the pre-built Kuzu graph index — empirically "
            "pinned by patching Path.read_text/ast.parse after the build and "
            "confirming zero calls across depends_on/breaks_if_removed/dependents_of.",
            ("Path.read_text / ast.parse call count during queries: 0",),
        )
    else:
        report.add_requirement(
            "avoid_single_prompt", "Avoid loading repository into a single prompt", Verdict.FAIL,
            f"a query path re-read source or re-parsed during a read: {reread_calls}",
        )

    # --- per-case rows ---
    report.add_case("depends_on:manager.py", "recalled", f"{len(deps)} direct imports")
    report.add_case("breaks_if_removed:store.py", "recalled", f"{len(breaks)} files")
    report.add_case("dependents_of:foundation (hops=1)", "recalled", f"{len(f1)} files")
    report.add_case("dependents_of:foundation (hops=20)", "recalled", f"{len(f20)} files")
    report.add_case("cross_batch:DERIVED_FROM(2 tasks)", "recalled",
                     f"{len(cb_fact_ids)} facts, each traced back to its own task")

    report.add_note(
        "scenario: Clannon's own real backend/ tree (not a synthetic fixture) — "
        "CB2's own 'Examples' list names Clannon first, and the point of this "
        "benchmark is demonstrating understanding of a repo too large for one "
        "prompt, which a toy fixture would undersell.")
    report.add_note(
        "file/edge counts drift under routine work (repo had 277 files / 889 edges "
        "when this harness was written) — assertions use floors well below that, "
        "plus a small set of structurally durable facts (e.g. manager.py depends_on "
        "store.py), not exact counts, same tension C4 solves with _MIN_ADRS.")
    report.add_note(
        "out of scope, matching the gap analysis's 'thin slice, not a graph-web' "
        "framing: behavioral/data-flow questions ('how does auth propagate'), the "
        "architectural-boundary narrative ('what boundaries exist'), and the other "
        "four graph types (file/architectural/decision/ownership) beyond the "
        "dependency graph built here.")
    report.add_note(
        "file-level granularity only (no per-symbol/function-level nodes) and "
        "Python-only (the ast extractor does not walk the TypeScript frontend) — "
        "the same honest limits scripts/cb2_repo_intelligence_demo.py documents.")
    report.add_note(
        "'CB2 (full)' per the ratified knowledge-web design (§5) also needs "
        "symbol-granularity traversal (function/struct-level, not just file-level) "
        "— that's the code-symbol tier (§3.3), a cross-tree dependency on "
        "orchestration's extractor, NOT built here. cross_batch_knowledge above "
        "proves the OTHER half of 'full' (shared-graph, multi-batch traceability) "
        "that doesn't need it.")
    report.add_note("serves Critical Benchmark 2 (Large Repository Understanding), thin slice.")

    return report


def run() -> BenchmarkReport:
    """Entry point for the consolidated scoreboard (scripts/benchmarks/run_all.py)."""
    with _disposable_graph_db():
        probe = asyncio.run(_run_probe())
    return _build_report(probe)


# ---------------------------------------------------------------------------
# Pytest entry points
# ---------------------------------------------------------------------------

def test_c2_repo_intelligence_probe():
    """Critical Benchmark 2 thin slice: build the real code-import graph over
    Clannon's own backend/ tree, then answer CB2-shaped questions through the
    port. Never fakes a pass — see _build_report for exactly what is and
    isn't shown."""
    report = run()
    print("\n" + report.render())

    assert not report.has_failure(), (
        "a genuine defect was found, not just an honest gap:\n" + report.render()
    )
    by_key = {r.key: r for r in report.requirements}
    for key in ("navigate", "trace_dependencies", "follow_relationships",
                "cross_batch_knowledge", "avoid_single_prompt"):
        assert by_key[key].verdict is Verdict.PASS, "\n" + report.render()
    assert by_key["architectural_explanations"].verdict is Verdict.NOT_YET, "\n" + report.render()


def test_probe_floor_counts_hold():
    """Separate from the requirement scoring above: pins the durable-structure
    floors directly against the raw extractor output, independent of the port
    adaptation layer."""
    from core.memory.graph_extract import build_code_import_graph

    graph = build_code_import_graph(_BACKEND_ROOT)
    assert len(graph.nodes) >= _MIN_FILES, len(graph.nodes)
    assert len(graph.edges) >= _MIN_EDGES, len(graph.edges)


def test_report_renders_structured_block(capsys):
    report = run()
    print(report.render())
    captured = capsys.readouterr().out
    assert "BENCHMARK C2" in captured
    assert "OVERALL:" in captured
    for key in ("navigate", "trace_dependencies", "follow_relationships",
                "cross_batch_knowledge", "architectural_explanations", "avoid_single_prompt"):
        assert key in captured


if __name__ == "__main__":
    print(run().render())
