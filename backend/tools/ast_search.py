"""AST-aware code search (key: code.ast_search) — finds a symbol's definitions and
call-sites STRUCTURALLY (via a real parse), not by text/grep match. The CB2
large-repo flagship: `code.engineer` gains a sharper instrument for navigating a
repo extracted into its workspace (`ExpertHandler._extract_archive`), the same way
`fs.patch` sharpened it for precise editing.

Two languages, per the ratified design (`proposals/archive/to-backend/
2026-07-25_nav-patch-tooling-design.md` §4): Python (this codebase) and C (the
CB2 large-repo benchmark target). A file is scanned by its extension; unsupported
extensions are skipped, never erroring the whole search. Add a language only when
a real consumer needs it — don't grow this speculatively.

v1 scope, explicit not silent: PLAIN-NAME matches only — a bare `identifier` call
(`foo(x)`) or a function/class/struct/union/enum definition. An attribute/method
call (`obj.foo(x)`) is not matched (the callee is an `attribute` node, not a bare
`identifier`) — a fast-follow, not silently claimed as covered.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from foundation import PermissionLevel, WorkspacePort

from registry import tool

from tree_sitter import Node

from tools._treesitter import EXT_LANGUAGE as _EXT_LANGUAGE, PARSERS as _PARSERS

_MAX_FILES_SCANNED = 500     # bounds scan cost across a large repo
_MAX_MATCHES = 200           # bounds the result payload
_MAX_FILE_BYTES = 2_000_000  # skip parsing anything past this (not a text file, or absurdly large)

# node types that DEFINE a symbol, per language, and how to pull the name node out
# of one: python exposes a "name" field directly; C's function name sits behind a
# chain of declarator wrapper nodes (pointer/array/parenthesized), so it needs a walk.
_PY_DEF_TYPES = ("function_definition", "class_definition")
_C_NAMED_DEF_TYPES = ("struct_specifier", "union_specifier", "enum_specifier")


def _c_declarator_name(node: Node | None) -> Node | None:
    """Walk a C declarator chain (pointer/array/parenthesized/function) down to the
    plain identifier at its core — a function's name is never the declarator's own
    top node once a `*`/`[]`/`()` wrapper is involved."""
    while node is not None and node.type != "identifier":
        node = node.child_by_field_name("declarator")
    return node


def _matches(node: Node, name: str) -> bool:
    return node is not None and node.type in ("identifier", "type_identifier") and node.text == name.encode()


def _walk(node: Node, language: str, name: str, kind_filter: str, out: list[tuple[str, Node, str]]) -> None:
    """Depth-first; appends (kind, name_node, defining_node_type) for every
    definition/call match of `name` that also matches `kind_filter` ('definition',
    'reference', or 'any') — filtered HERE, not after collection, so the per-call
    `_MAX_MATCHES` cap counts only what the caller actually asked for. A `kind=
    'definition'` search against a file dense with call-sites must not let those
    references eat the whole cap and silently push the real definition (later in
    the same file) out of the result. `name_node` is reported for an accurate
    line/column; `defining_node_type` is recorded explicitly here (the outer
    definition/call node's own `.type`) rather than inferred from `name_node.
    parent` afterward — a C function's name sits several declarator-wrapper
    levels below `function_definition`, so that inference would be wrong."""
    if len(out) >= _MAX_MATCHES:
        return
    want_def = kind_filter in ("any", "definition")
    want_ref = kind_filter in ("any", "reference")
    if language == "python":
        if want_def and node.type in _PY_DEF_TYPES:
            n = node.child_by_field_name("name")
            if _matches(n, name):
                out.append(("definition", n, node.type))
        elif want_ref and node.type == "call":
            fn = node.child_by_field_name("function")
            if _matches(fn, name):
                out.append(("reference", fn, node.type))
    else:  # c
        if want_def and node.type == "function_definition":
            n = _c_declarator_name(node.child_by_field_name("declarator"))
            if _matches(n, name):
                out.append(("definition", n, node.type))
        elif want_def and node.type in _C_NAMED_DEF_TYPES:
            n = node.child_by_field_name("name")
            if _matches(n, name):
                out.append(("definition", n, node.type))
        elif want_ref and node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if _matches(fn, name):
                out.append(("reference", fn, node.type))
    for child in node.children:
        if len(out) >= _MAX_MATCHES:
            return
        _walk(child, language, name, kind_filter, out)


class AstSearchIn(BaseModel):
    name: str = Field(min_length=1, description="Exact symbol name to find (a function, class, struct/union/enum, or call-site).")
    kind: str = Field(
        default="any",
        description="Which matches to return: 'definition', 'reference' (call-sites), or 'any' (both, default).",
    )
    language: str | None = Field(
        default=None,
        description="Restrict the scan to one language ('python' or 'c'). Omit to scan every supported file.",
    )
    path_prefix: str = Field(
        default="", description="Workspace-relative directory to scope the scan to, e.g. 'src/'. Omit to scan the whole workspace.",
    )

    @model_validator(mode="after")
    def _kind_and_language_are_valid(self) -> "AstSearchIn":
        if self.kind not in ("definition", "reference", "any"):
            raise ValueError("kind must be 'definition', 'reference', or 'any'")
        if self.language is not None and self.language not in _PARSERS:
            raise ValueError(f"language must be one of {sorted(_PARSERS)}")
        return self


class AstMatch(BaseModel):
    path: str
    line: int
    column: int
    kind: str        # "definition" | "reference"
    node_type: str    # the AST node type that defined/called it (e.g. "function_definition")
    snippet: str      # the source line, for context


class AstSearchOut(BaseModel):
    ok: bool
    matches: list[AstMatch] = Field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0    # candidate files NOT scanned (too large, unreadable, or past the file-count cap)
    truncated: bool = False   # true if files_skipped > 0 OR the match cap was hit — results are not exhaustive
    error: str = ""


@tool
class AstSearchTool:
    name = "ast_search"
    domain = "code"
    description = (
        "Find every definition and call-site of an exact symbol name across the workspace, via a real "
        "AST parse (Python and C) — not a text/grep match, so it won't false-positive on a comment or "
        "string containing the name. Use this before editing a function/class/struct you didn't just "
        "write yourself, to see where else it's defined or called. Matches plain-name calls only "
        "(foo(x)), not attribute/method calls (obj.foo(x))."
    )
    input_schema = AstSearchIn
    output_schema = AstSearchOut
    permission = PermissionLevel.READ
    wants_workspace = True

    async def run(self, args: AstSearchIn, workspace: WorkspacePort) -> AstSearchOut:
        try:
            all_paths = await workspace.list()
        except Exception as exc:  # noqa: BLE001 — confinement/IO error -> structured failure
            return AstSearchOut(ok=False, error=str(exc)[:200])

        candidates = [
            p for p in all_paths
            if not args.path_prefix or p.startswith(args.path_prefix)
        ]
        targets: list[tuple[str, str]] = []  # (path, language)
        for p in candidates:
            ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
            lang = _EXT_LANGUAGE.get(ext)
            if lang is None or (args.language is not None and lang != args.language):
                continue
            targets.append((p, lang))

        skipped = max(0, len(targets) - _MAX_FILES_SCANNED)
        targets = targets[:_MAX_FILES_SCANNED]

        matches: list[AstMatch] = []
        scanned = 0
        truncated = skipped > 0
        for i, (path, lang) in enumerate(targets):
            if len(matches) >= _MAX_MATCHES:
                truncated = True
                skipped += len(targets) - i
                break
            try:
                data = await workspace.read_bytes(path)
            except Exception:  # noqa: BLE001 — one unreadable file must not sink the search
                skipped += 1
                truncated = True
                continue
            if len(data) > _MAX_FILE_BYTES:
                skipped += 1
                truncated = True
                continue
            scanned += 1
            tree = _PARSERS[lang].parse(data)
            found: list[tuple[str, Node, str]] = []
            _walk(tree.root_node, lang, args.name, args.kind, found)
            if len(found) >= _MAX_MATCHES:
                truncated = True   # this file alone may hold more matches than we collected
            lines = data.split(b"\n")
            for kind, node, node_type in found:
                if len(matches) >= _MAX_MATCHES:
                    truncated = True
                    break
                row, col = node.start_point
                snippet = lines[row].decode("utf-8", "replace").strip() if row < len(lines) else ""
                matches.append(AstMatch(
                    path=path, line=row + 1, column=col, kind=kind,
                    node_type=node_type, snippet=snippet,
                ))

        return AstSearchOut(ok=True, matches=matches, files_scanned=scanned, files_skipped=skipped, truncated=truncated)
