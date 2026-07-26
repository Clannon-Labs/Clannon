"""Dependency-graph traversal (key: code.dep_graph) — BFS over import/include edges,
extracted via the same tree-sitter parses as code.ast_search (Python `import`/`from`
statements, C `#include` directives), outward from a starting file. §5 of the ratified
nav-patch-tooling design (`proposals/archive/to-backend/2026-07-25_nav-patch-tooling-
design.md`), built on §4's AST tool per that design's own build order — a file's import
edges are extracted the same structural way `code.ast_search` extracts symbol
definitions, not by text match.

v1 scope, explicit not silent:
- No persisted graph. Edges are recomputed fresh on every call by scanning the
  workspace (the workspace itself is ephemeral, per-call — nothing to persist yet).
- Resolution is best-effort STRUCTURAL matching against the actual file listing, not a
  real import resolver: no sys.path / -I search-path semantics, no partial-package
  fallback, no basename-guessing. An import that doesn't resolve to a real workspace
  file is recorded as an UNRESOLVED edge (raw text preserved, `target=""`), never
  silently dropped — the caller sees "this file imports X, couldn't find it" rather
  than a gap.
- Python relative imports (`from . import x`): a single leading dot is treated as the
  importing file's OWN directory, each further dot goes up one more level — an
  approximation of the real package-vs-module distinction (which needs `__init__.py`
  layout knowledge this tool doesn't have), stated here so it isn't mistaken for exact
  language-spec semantics.
- `from X import y`: only the module `X` is resolved as an edge target; the imported
  NAME `y` is not — dep-graph traversal is file-to-file, not symbol-level (that's
  `code.ast_search`'s job).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from foundation import PermissionLevel, WorkspacePort

from registry import tool

from tree_sitter import Node

from tools._treesitter import EXT_LANGUAGE as _EXT_LANGUAGE, PARSERS as _PARSERS

_MAX_FILES_SCANNED = 500     # bounds the index-build scan cost across a large repo
_MAX_FILE_BYTES = 2_000_000  # skip parsing anything past this (not a text file, or absurdly large)
_MAX_EDGES = 2_000           # bounds the extracted edge index
_MAX_NODES = 200             # bounds the BFS traversal result
_MAX_DEPTH = 10              # hard ceiling on the caller's max_depth


class DepEdge(BaseModel):
    source: str
    target: str    # "" if unresolved
    raw: str        # the import/include text as written in source
    resolved: bool


def _resolve_python_module(dotted: str, workspace_paths: set[str]) -> str | None:
    rel = dotted.replace(".", "/")
    for candidate in (f"{rel}.py", f"{rel}/__init__.py"):
        if candidate in workspace_paths:
            return candidate
    return None


def _relative_parts(node: Node) -> tuple[int, str]:
    """A `relative_import` node's leading-dot count + optional trailing dotted-name tail."""
    prefix = next((c for c in node.children if c.type == "import_prefix"), None)
    level = sum(1 for c in prefix.children if c.type == ".") if prefix is not None else 0
    tail_node = next((c for c in node.children if c.type == "dotted_name"), None)
    tail = tail_node.text.decode() if tail_node is not None else ""
    return level, tail


def _resolve_python_relative(level: int, tail: str, source_path: str, workspace_paths: set[str]) -> str | None:
    parts = source_path.split("/")[:-1]   # importing file's own directory, one dot = here
    up = level - 1
    if up > len(parts):
        return None
    if up:
        parts = parts[:-up]
    if tail:
        parts = parts + tail.split(".")
        candidates = ("/".join(parts) + ".py", "/".join(parts) + "/__init__.py")
    elif parts:
        candidates = ("/".join(parts) + "/__init__.py",)
    else:
        candidates = ("__init__.py",)
    for candidate in candidates:
        if candidate in workspace_paths:
            return candidate
    return None


def _resolve_c_include(raw: str, source_path: str, workspace_paths: set[str]) -> str | None:
    base_dir = source_path.rsplit("/", 1)[0] if "/" in source_path else ""
    parts: list[str] = base_dir.split("/") if base_dir else []
    for segment in raw.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
            continue
        parts.append(segment)
    candidate = "/".join(parts)
    return candidate if candidate in workspace_paths else None


def _extract_python_edges(root: Node, source_path: str, workspace_paths: set[str]) -> list[DepEdge]:
    out: list[DepEdge] = []

    def walk(node: Node) -> None:
        if node.type == "import_statement":
            for child in node.children:
                name_node = child if child.type == "dotted_name" else (
                    child.child_by_field_name("name") if child.type == "aliased_import" else None
                )
                if name_node is not None:
                    dotted = name_node.text.decode()
                    target = _resolve_python_module(dotted, workspace_paths)
                    out.append(DepEdge(source=source_path, target=target or "", raw=dotted, resolved=target is not None))
        elif node.type == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            if mod is not None and mod.type == "dotted_name":
                dotted = mod.text.decode()
                target = _resolve_python_module(dotted, workspace_paths)
                out.append(DepEdge(source=source_path, target=target or "", raw=dotted, resolved=target is not None))
            elif mod is not None and mod.type == "relative_import":
                level, tail = _relative_parts(mod)
                target = _resolve_python_relative(level, tail, source_path, workspace_paths)
                raw = "." * level + tail
                out.append(DepEdge(source=source_path, target=target or "", raw=raw, resolved=target is not None))
        for child in node.children:
            walk(child)

    walk(root)
    return out


def _extract_c_edges(root: Node, source_path: str, workspace_paths: set[str]) -> list[DepEdge]:
    out: list[DepEdge] = []

    def walk(node: Node) -> None:
        if node.type == "preproc_include":
            path_node = node.child_by_field_name("path")
            if path_node is not None and path_node.type == "string_literal":
                content = next((c for c in path_node.children if c.type == "string_content"), None)
                raw = content.text.decode() if content is not None else ""
                target = _resolve_c_include(raw, source_path, workspace_paths) if raw else None
                out.append(DepEdge(source=source_path, target=target or "", raw=raw, resolved=target is not None))
            elif path_node is not None and path_node.type == "system_lib_string":
                raw = path_node.text.decode().strip("<>")
                out.append(DepEdge(source=source_path, target="", raw=raw, resolved=False))
        for child in node.children:
            walk(child)

    walk(root)
    return out


_EXTRACTORS = {"python": _extract_python_edges, "c": _extract_c_edges}


class DepGraphIn(BaseModel):
    start_path: str = Field(min_length=1, description="Workspace-relative file to start the traversal from.")
    direction: str = Field(
        default="dependencies",
        description="'dependencies' (what start_path imports, outgoing), 'dependents' (what imports start_path, "
                    "incoming), or 'both'.",
    )
    max_depth: int = Field(default=3, ge=1, le=_MAX_DEPTH, description="How many import hops to follow from start_path.")
    path_prefix: str = Field(
        default="", description="Workspace-relative directory to scope the underlying scan to, e.g. 'src/'. "
                                 "Omit to scan the whole workspace.",
    )

    @model_validator(mode="after")
    def _direction_is_valid(self) -> "DepGraphIn":
        if self.direction not in ("dependencies", "dependents", "both"):
            raise ValueError("direction must be 'dependencies', 'dependents', or 'both'")
        return self


class DepNode(BaseModel):
    path: str
    depth: int


class DepGraphOut(BaseModel):
    ok: bool
    start_path: str = ""
    nodes: list[DepNode] = Field(default_factory=list)
    edges: list[DepEdge] = Field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0
    truncated: bool = False
    error: str = ""


@tool
class DepGraphTool:
    name = "dep_graph"
    domain = "code"
    description = (
        "Traverse a repo's import/include graph outward from one file, via a real AST parse (Python and C) — "
        "not a text/grep match. 'dependencies' finds what a file imports (transitively, bounded by max_depth); "
        "'dependents' finds what imports it. Use this before editing or removing a file, to see what would break."
    )
    input_schema = DepGraphIn
    output_schema = DepGraphOut
    permission = PermissionLevel.READ
    wants_workspace = True

    async def run(self, args: DepGraphIn, workspace: WorkspacePort) -> DepGraphOut:
        try:
            all_paths = await workspace.list()
        except Exception as exc:  # noqa: BLE001 — confinement/IO error -> structured failure
            return DepGraphOut(ok=False, error=str(exc)[:200])

        workspace_paths = set(all_paths)
        if args.start_path not in workspace_paths:
            return DepGraphOut(ok=False, error=f"start_path not found in workspace: {args.start_path}")

        candidates = [p for p in all_paths if not args.path_prefix or p.startswith(args.path_prefix)]
        targets: list[tuple[str, str]] = []  # (path, language)
        for p in candidates:
            ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
            lang = _EXT_LANGUAGE.get(ext)
            if lang is not None:
                targets.append((p, lang))

        skipped = max(0, len(targets) - _MAX_FILES_SCANNED)
        targets = targets[:_MAX_FILES_SCANNED]

        forward: dict[str, list[DepEdge]] = {}
        scanned = 0
        truncated = skipped > 0
        total_edges = 0
        for i, (path, lang) in enumerate(targets):
            if total_edges >= _MAX_EDGES:
                truncated = True
                skipped += len(targets) - i
                break
            try:
                data = await workspace.read_bytes(path)
            except Exception:  # noqa: BLE001 — one unreadable file must not sink the whole traversal
                skipped += 1
                truncated = True
                continue
            if len(data) > _MAX_FILE_BYTES:
                skipped += 1
                truncated = True
                continue
            scanned += 1
            tree = _PARSERS[lang].parse(data)
            edges = _EXTRACTORS[lang](tree.root_node, path, workspace_paths)
            if total_edges + len(edges) > _MAX_EDGES:
                edges = edges[: _MAX_EDGES - total_edges]
                truncated = True
            total_edges += len(edges)
            if edges:
                forward[path] = edges

        reverse: dict[str, list[DepEdge]] = {}
        for edges in forward.values():
            for e in edges:
                if e.resolved:
                    reverse.setdefault(e.target, []).append(e)

        want_deps = args.direction in ("dependencies", "both")
        want_dependents = args.direction in ("dependents", "both")

        visited: dict[str, int] = {args.start_path: 0}
        result_edges: list[DepEdge] = []
        seen_edges: set[tuple[str, str]] = set()
        node_cap_hit = False
        frontier = [args.start_path]
        depth = 0
        while frontier and depth < args.max_depth:
            next_frontier: list[str] = []
            for path in frontier:
                if want_deps:
                    for e in forward.get(path, []):
                        key = (e.source, e.raw)
                        if key not in seen_edges:
                            seen_edges.add(key)
                            result_edges.append(e)
                        if e.resolved and e.target not in visited:
                            if len(visited) >= _MAX_NODES:
                                node_cap_hit = True
                                continue
                            visited[e.target] = depth + 1
                            next_frontier.append(e.target)
                if want_dependents:
                    for e in reverse.get(path, []):
                        key = (e.source, e.raw)
                        if key not in seen_edges:
                            seen_edges.add(key)
                            result_edges.append(e)
                        if e.source not in visited:
                            if len(visited) >= _MAX_NODES:
                                node_cap_hit = True
                                continue
                            visited[e.source] = depth + 1
                            next_frontier.append(e.source)
            frontier = next_frontier
            depth += 1

        nodes = [DepNode(path=p, depth=d) for p, d in sorted(visited.items(), key=lambda kv: (kv[1], kv[0]))]
        return DepGraphOut(
            ok=True, start_path=args.start_path, nodes=nodes, edges=result_edges,
            files_scanned=scanned, files_skipped=skipped, truncated=truncated or node_cap_hit,
        )
