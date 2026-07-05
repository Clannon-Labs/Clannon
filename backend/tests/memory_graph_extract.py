"""
The first-slice CB2 extractor — behavioural proof that
`core.memory.graph_extract.build_code_import_graph` produces a correct file
node/import edge graph, and that `depends_on`/`dependents_of`/
`breaks_if_removed` answer the three questions the GraphPort design promises
(`proposals/archive/to-backend/2026-07-05_graph-port-design.md` §5):

  ✓ absolute `import x`, `from x import y`, and relative `from .. import y`
    all resolve to the correct internal file edge
  ✓ stdlib/third-party imports produce NO edge (not internal — this is a
    repo-module graph, not a full dependency closure)
  ✓ a file that fails to parse (syntax error) still becomes a node, never
    aborts the whole build (degrade, don't raise)
  ✓ depends_on / dependents_of are correct inverses, both hop-bounded
  ✓ breaks_if_removed is the transitive closure of dependents_of
  ✓ smoke-tested against the REAL backend/ tree — a known real edge
    (`core/memory/manager.py` -> `core/memory/store.py`) is actually found,
    so this isn't just passing against a synthetic fixture

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_graph_extract.py -v
"""
from __future__ import annotations

from pathlib import Path

from core.memory.graph_extract import build_code_import_graph

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic fixtures — absolute imports
# ─────────────────────────────────────────────────────────────────────────────

def test_absolute_import_and_from_import_resolve_to_internal_edges(tmp_path):
    (tmp_path / "a.py").write_text("VALUE = 1\n")
    (tmp_path / "b.py").write_text("import a\n")
    (tmp_path / "c.py").write_text("from a import VALUE\nimport b\n")

    graph = build_code_import_graph(tmp_path)

    assert graph.nodes == frozenset({"a.py", "b.py", "c.py"})
    assert ("b.py", "a.py") in graph.edges
    assert ("c.py", "a.py") in graph.edges
    assert ("c.py", "b.py") in graph.edges


def test_stdlib_and_third_party_imports_produce_no_edge(tmp_path):
    (tmp_path / "a.py").write_text("import os\nimport sys\nfrom collections import OrderedDict\n")

    graph = build_code_import_graph(tmp_path)

    assert graph.nodes == frozenset({"a.py"})
    assert graph.edges == frozenset()


def test_syntax_error_file_becomes_a_node_with_no_edges_not_a_crash(tmp_path):
    (tmp_path / "broken.py").write_text("def f(:\n    pass\n")
    (tmp_path / "fine.py").write_text("import broken\n")

    graph = build_code_import_graph(tmp_path)

    assert "broken.py" in graph.nodes
    assert "fine.py" in graph.nodes
    # broken.py couldn't be parsed for its OWN imports, but it can still be
    # imported BY something else — that edge comes from the importing side.
    assert ("fine.py", "broken.py") in graph.edges


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic fixture — relative imports across a real package structure
# ─────────────────────────────────────────────────────────────────────────────

def test_relative_imports_resolve_across_packages(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod1.py").write_text("VALUE = 1\n")
    sub = pkg / "sub"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    (sub / "mod2.py").write_text("from .. import mod1\n")

    graph = build_code_import_graph(tmp_path)

    # "from .. import mod1" in pkg/sub/mod2.py resolves through pkg/__init__.py
    # (the base of the relative import) AND pkg/mod1.py (the named submodule).
    assert ("pkg/sub/mod2.py", "pkg/__init__.py") in graph.edges
    assert ("pkg/sub/mod2.py", "pkg/mod1.py") in graph.edges


# ─────────────────────────────────────────────────────────────────────────────
# depends_on / dependents_of / breaks_if_removed — the three CB2 questions
# ─────────────────────────────────────────────────────────────────────────────

def _linear_chain_graph(tmp_path) -> Path:
    """c.py -> b.py -> a.py (c depends on b, b depends on a)."""
    (tmp_path / "a.py").write_text("VALUE = 1\n")
    (tmp_path / "b.py").write_text("import a\n")
    (tmp_path / "c.py").write_text("import b\n")
    return tmp_path


def test_depends_on_is_hop_bounded(tmp_path):
    graph = build_code_import_graph(_linear_chain_graph(tmp_path))

    assert graph.depends_on("c.py", max_hops=1) == frozenset({"b.py"})
    assert graph.depends_on("c.py", max_hops=2) == frozenset({"b.py", "a.py"})


def test_dependents_of_is_the_inverse_of_depends_on(tmp_path):
    graph = build_code_import_graph(_linear_chain_graph(tmp_path))

    assert graph.dependents_of("a.py", max_hops=1) == frozenset({"b.py"})
    assert graph.dependents_of("a.py", max_hops=2) == frozenset({"b.py", "c.py"})


def test_breaks_if_removed_is_transitive_closure_of_dependents(tmp_path):
    graph = build_code_import_graph(_linear_chain_graph(tmp_path))

    # Default max_hops is generous enough to cover the whole chain without
    # the caller having to guess a depth.
    assert graph.breaks_if_removed("a.py") == frozenset({"b.py", "c.py"})
    # Nothing depends on the leaf of the chain.
    assert graph.breaks_if_removed("c.py") == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test against the REAL backend/ tree
# ─────────────────────────────────────────────────────────────────────────────

def test_real_backend_tree_produces_a_known_edge():
    graph = build_code_import_graph(_BACKEND_ROOT)

    assert "core/memory/manager.py" in graph.nodes
    assert "core/memory/store.py" in graph.nodes
    # manager.py does `from . import embeddings, store, writer`.
    assert ("core/memory/manager.py", "core/memory/store.py") in graph.edges
    # Removing store.py would break manager.py — proves breaks_if_removed
    # sees through the real repo's actual import shape, not just a fixture.
    assert "core/memory/manager.py" in graph.breaks_if_removed("core/memory/store.py")
