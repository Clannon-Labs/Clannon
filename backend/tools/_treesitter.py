"""Shared tree-sitter setup for AST-based tools (code.ast_search, code.dep_graph) —
one parser instance per language, one file-extension->language map, so each new
tree-sitter-backed tool doesn't reinstantiate its own copy of the same infra."""

from __future__ import annotations

import tree_sitter_c as tsc
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

EXT_LANGUAGE = {"py": "python", "c": "c", "h": "c"}

PARSERS = {
    "python": Parser(Language(tspython.language())),
    "c": Parser(Language(tsc.language())),
}
