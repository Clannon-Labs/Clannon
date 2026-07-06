"""
core/memory/graph_extract.py

Pure, dependency-free extraction of a code import graph over a Python source
tree — the first-slice CB2 extractor
(`proposals/archive/to-backend/2026-07-05_graph-port-design.md` §5).

Parses every `.py` file with `ast` (not a regex grep like `check_invariants.py`
— resolves relative imports and aliases a text scan can't) and produces
file-level nodes plus internal import edges. Only imports that resolve to
another file under the same root are tracked — stdlib/third-party imports are
not nodes in this graph; this is a dependency graph over the repo's own
modules, not a transitive closure over installed packages.

Deliberately independent of `GraphPort`/Kuzu: no graph-substrate dependency,
buildable and testable before the foundation contract lands (the one import
below, `settings`, is lightweight config, not graph infra — `breaks_if_removed`'s
hop-ceiling default reads the same config value `graph_store.MAX_HOPS_CEILING`
does, rather than hardcoding a second copy that could drift). `graph_manager.py`
is the (future) adapter that turns a `CodeImportGraph` into `GraphNode`/`GraphEdge`
writes through the door.

Honest limits: no macro/dynamic-import resolution, star imports contribute
only the base-module edge (not per-name resolution), best-effort on unusual
import shapes — same "honest limit" precedent as the graph-stack doc's note on
unresolvable function pointers.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import settings

_EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".git"}


@dataclass(frozen=True, slots=True)
class CodeImportGraph:
    """The first-slice code graph: repo-relative, posix-style file paths as
    nodes, directed (importer -> imported) internal-only import edges."""
    nodes: frozenset[str] = field(default_factory=frozenset)
    edges: frozenset[tuple[str, str]] = field(default_factory=frozenset)

    def depends_on(self, path: str, *, max_hops: int = 1) -> frozenset[str]:
        """Files `path` imports (directly, or transitively up to max_hops)."""
        return _walk(self.edges, {path}, max_hops, forward=True) - {path}

    def dependents_of(self, path: str, *, max_hops: int = 1) -> frozenset[str]:
        """Files that import `path` (directly, or transitively up to max_hops)."""
        return _walk(self.edges, {path}, max_hops, forward=False) - {path}

    def breaks_if_removed(
        self, path: str, *, max_hops: int = settings.MEMORY.graph_max_hops_ceiling
    ) -> frozenset[str]:
        """Transitive closure of dependents_of — every file whose import chain
        would break if `path` disappeared. Hop-bounded (default from the same
        `graph_max_hops_ceiling` config value `graph_store.MAX_HOPS_CEILING`
        reads — a single source, not a second hardcoded literal that could
        drift from it; read directly from `settings` rather than importing
        `graph_store` to avoid a circular import, since `graph_store.py`
        itself imports THIS module) so a cyclic/dense graph can't hang the
        query."""
        return self.dependents_of(path, max_hops=max_hops)


def _walk(
    edges: frozenset[tuple[str, str]],
    frontier: set[str],
    max_hops: int,
    *,
    forward: bool,
) -> frozenset[str]:
    seen = set(frontier)
    index: dict[str, list[str]] = {}
    for src, dst in edges:
        key, val = (src, dst) if forward else (dst, src)
        index.setdefault(key, []).append(val)
    for _ in range(max_hops):
        nxt = {
            neighbor
            for node in frontier
            for neighbor in index.get(node, ())
            if neighbor not in seen
        }
        if not nxt:
            break
        seen |= nxt
        frontier = nxt
    return frozenset(seen)


def build_code_import_graph(root: Path) -> CodeImportGraph:
    """Walk `root` (a Python source tree, e.g. `backend/`), parse every `.py`
    file, and return its internal import graph. A file that fails to parse
    (syntax error) becomes a node with no outgoing edges rather than aborting
    the build — degrade, don't raise, even though this is an offline/batch
    build rather than a turn-time call."""
    root = root.resolve()
    files = sorted(
        p for p in root.rglob("*.py")
        if not any(part in _EXCLUDE_DIRS for part in p.parts)
    )
    rel_paths = {p: p.relative_to(root).as_posix() for p in files}
    nodes = frozenset(rel_paths.values())

    edges: set[tuple[str, str]] = set()
    for path in files:
        src_rel = rel_paths[path]
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8", errors="replace"),
                filename=str(path),
            )
        except SyntaxError:
            continue
        package = _file_package(path, root)
        for node in ast.walk(tree):
            for module in _imported_modules(node, package):
                dst = _module_to_relpath(module, root)
                if dst is not None and dst in nodes and dst != src_rel:
                    edges.add((src_rel, dst))

    return CodeImportGraph(nodes=nodes, edges=frozenset(edges))


def _file_package(path: Path, root: Path) -> str:
    """Dotted package path of the directory containing `path`, relative to
    root — correct for both a plain module and an `__init__.py` (a package's
    own `__package__` equals its own dotted name)."""
    rel_dir = path.parent.relative_to(root)
    return ".".join(rel_dir.parts)


def _resolve_relative(package: str, level: int, module: str) -> str:
    """Mirrors `importlib._bootstrap._resolve_name` — turns a relative
    `from ..x import y` into the absolute dotted module name it targets."""
    bits = package.rsplit(".", level - 1)
    base = bits[0]
    return f"{base}.{module}" if module else base


def _imported_modules(node: ast.AST, package: str) -> list[str]:
    """Every absolute dotted module name a single Import/ImportFrom statement
    references: the base module always, plus each `from X import name` name
    as a submodule candidate (resolved away downstream if it isn't one)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level:
            if not package:
                return []
            base = _resolve_relative(package, node.level, node.module or "")
        else:
            base = node.module or ""
        if not base:
            return []
        out = [base]
        out.extend(
            f"{base}.{alias.name}" for alias in node.names if alias.name != "*"
        )
        return out
    return []


def _module_to_relpath(module: str, root: Path) -> str | None:
    """Absolute dotted module name -> repo-relative `.py` path, or None if it
    isn't a file under root (stdlib/third-party — not tracked in this graph)."""
    candidate = root.joinpath(*module.split("."))
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return py_file.relative_to(root).as_posix()
    init_file = candidate / "__init__.py"
    if init_file.is_file():
        return init_file.relative_to(root).as_posix()
    return None
