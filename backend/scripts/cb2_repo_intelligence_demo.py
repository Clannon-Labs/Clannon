#!/usr/bin/env python3
"""
CB2 — Large Repository Understanding — thin-slice proof
Critical Benchmark 2 (docs/benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md)

═══════════════════════════════════════════════════════════════════════
WHAT THIS DEMONSTRATES
═══════════════════════════════════════════════════════════════════════

The question CB2 asks: can the system answer "what depends on Y" / "what
breaks if X is removed" over a repository LARGER THAN ITS CONTEXT WINDOW,
without prompt-stuffing the whole tree into a model call?

This script builds the code-import graph over Clannon's OWN backend/ tree
(via `core.memory.graph_extract`'s `ast`-based extractor — the thin first
slice from `proposals/archive/to-backend/2026-07-05_graph-port-design.md`
§5), persists it through `GraphManager` (the sole `GraphPort` implementer,
Kuzu-backed), and then answers three real questions by walking the GRAPH —
not by re-reading source, not by asking a model to reason over pasted
files. Every answer below comes from `depends_on`/`dependents_of`/
`breaks_if_removed`, the exact three methods the port promises.

═══════════════════════════════════════════════════════════════════════
HONEST NOT-YET LABELS
═══════════════════════════════════════════════════════════════════════

This is the THIN first slice, not the full knowledge-web:

  • Per-symbol granularity  (function/struct/class-level nodes — today's
    graph is FILE-level only; tree-sitter/scip-clang symbol resolution is
    the documented next tier, not built)
  • Cross-language           (Python `ast` only — the TypeScript frontend
    is not walked; a second extractor would be a separate, later slice)
  • Entity/media fusion      (CB3's shared-entity/cross-media graph rides
    the same GraphPort but is explicitly out of scope here)
  • An expert/tool consumer  (a CB2-facing code-navigation expert that
    calls this port from a conversation turn is orchestration's tree to
    build — this script exercises the substrate directly, the way that
    future expert eventually would)

Static analysis also has the same honest limit noted in
docs/architecture/knowledge_graph/CLANNON_GRAPH_STACK.md: only imports
that resolve to a literal module path are tracked; dynamic/conditional
imports are invisible to this slice.

═══════════════════════════════════════════════════════════════════════
USAGE  (from repo root or backend/)
═══════════════════════════════════════════════════════════════════════

  python backend/scripts/cb2_repo_intelligence_demo.py
  python backend/scripts/cb2_repo_intelligence_demo.py --path core/orchestrator/orchestrator.py

Runs against a fresh, disposable Kuzu database in a temp directory each
time (never touches a real dev/prod graph db) — Kuzu is embedded, so unlike
the Qdrant memory demo there is no --live/hermetic distinction to make.
"""
from __future__ import annotations

# ── path bootstrap (works from any CWD: repo root or backend/) ──────────────
# Python always puts a directly-run script's own directory (scripts/) on
# sys.path[0], so this sibling import resolves before backend/ itself does.
from _pathboot import ensure_backend_on_path

_BACKEND = ensure_backend_on_path()

# ── stdlib ────────────────────────────────────────────────────────────────────
import argparse
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from foundation import GraphScope  # noqa: E402  (after path bootstrap)

from core.memory.graph_manager import GraphManager  # noqa: E402

_WIDTH = 70
_DEMO_SCOPE = GraphScope(user_id="system", repo_id="clannon-self")
# Two files known (and tested — tests/memory_graph_manager.py) to have a
# real import edge in THIS repo, used as the default demo targets so a
# fresh reader sees a concrete, verifiable answer rather than an empty one.
_DEFAULT_DEPENDER = "core/memory/manager.py"
_DEFAULT_DEPENDENCY = "core/memory/store.py"


def _banner(title: str) -> None:
    print("\n" + "═" * _WIDTH)
    pad = (_WIDTH - len(title) - 2) // 2
    print(f"{'═' * pad} {title} {'═' * (_WIDTH - pad - len(title) - 2)}")
    print("═" * _WIDTH)


def _section(title: str) -> None:
    print(f"\n{'─' * _WIDTH}")
    print(f"  {title}")
    print("─" * _WIDTH)


def _print_paths(paths: list[str], *, limit: int = 15) -> None:
    if not paths:
        print("    (none)")
        return
    for p in sorted(paths)[:limit]:
        print(f"    • {p}")
    if len(paths) > limit:
        print(f"    … and {len(paths) - limit} more")


async def run_demo(*, target_path: str) -> None:
    _banner("CB2  ·  Large Repository Understanding  ·  thin-slice proof")
    print(f"""
  Repo   : Clannon's own backend/ (this codebase)
  Scope  : user_id={_DEMO_SCOPE.user_id!r} repo_id={_DEMO_SCOPE.repo_id!r}
           (a fixed, explicit scope — never an absent-scope shortcut,
           per the ratified GraphPort design §6)
  Store  : disposable Kuzu db, temp dir, deleted at the end of this run
""")

    manager = GraphManager()

    _section("STEP 1 — build the code-import graph (ast, not a raw text scan)")
    build = await manager.build_code_graph(_DEMO_SCOPE, Path(_BACKEND))
    if build.degraded:
        print(f"  [DEGRADED] {build.notes}")
        return
    print(f"  {build.notes}")

    from core.memory import graph_store  # local import: only needed to mint node_ids for display

    depender_id = graph_store.node_id(_DEMO_SCOPE, _DEFAULT_DEPENDER)
    dependency_id = graph_store.node_id(_DEMO_SCOPE, _DEFAULT_DEPENDENCY)
    target_id = graph_store.node_id(_DEMO_SCOPE, target_path)

    _section(f"STEP 2 — depends_on({_DEFAULT_DEPENDER!r})")
    print(f'\n  "What does {_DEFAULT_DEPENDER} import?"\n')
    deps = await manager.depends_on(_DEMO_SCOPE, depender_id)
    _print_paths([n.properties["path"] for n in deps.nodes])

    _section(f"STEP 3 — dependents_of({_DEFAULT_DEPENDENCY!r})")
    print(f'\n  "What imports {_DEFAULT_DEPENDENCY} directly?"\n')
    dependents = await manager.dependents_of(_DEMO_SCOPE, dependency_id)
    _print_paths([n.properties["path"] for n in dependents.nodes])

    _section(f"STEP 4 — breaks_if_removed({_DEFAULT_DEPENDENCY!r})  ← the CB2 question")
    print(f'\n  "What would break, transitively, if {_DEFAULT_DEPENDENCY} disappeared?"\n')
    breaks = await manager.breaks_if_removed(_DEMO_SCOPE, dependency_id)
    paths = [n.properties["path"] for n in breaks.nodes]
    _print_paths(paths)
    print(f"\n  {len(paths)} file(s) total — answered by graph traversal, zero source re-read.")

    if target_path not in (_DEFAULT_DEPENDER, _DEFAULT_DEPENDENCY):
        _section(f"STEP 5 — your target: breaks_if_removed({target_path!r})")
        custom = await manager.breaks_if_removed(_DEMO_SCOPE, target_id)
        custom_paths = [n.properties["path"] for n in custom.nodes]
        if not custom.nodes and not custom.degraded:
            lookup = await manager.lookup(_DEMO_SCOPE, natural_key=target_path)
            if not lookup.nodes:
                print(f"\n  '{target_path}' was not found in the built graph — check the path")
        _print_paths(custom_paths)
        print(f"\n  {len(custom_paths)} file(s) total.")

    _section("END")
    print("""
  This is the thin credible slice, not the full knowledge-web: file-level,
  Python-only, code-only. It extends into per-symbol + cross-language +
  entity/media fusion later — same GraphPort, same discipline, additive.
""")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clannon CB2 repository-intelligence demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path",
        default=_DEFAULT_DEPENDENCY,
        metavar="REPO_RELATIVE_PATH",
        help=f"An extra file (relative to backend/) to run breaks_if_removed on "
             f"(default: {_DEFAULT_DEPENDENCY}, already shown in step 4)",
    )
    args = parser.parse_args()

    demo_dir = tempfile.mkdtemp(prefix="clannon-cb2-demo-")
    # Kuzu creates the db path itself — it must NOT already exist as a
    # directory, so nest one level under the mkdtemp() dir (which does).
    os.environ["VRAKSHA_GRAPH_DB_PATH"] = str(Path(demo_dir) / "graph_db")
    try:
        asyncio.run(run_demo(target_path=args.path))
    finally:
        shutil.rmtree(demo_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
