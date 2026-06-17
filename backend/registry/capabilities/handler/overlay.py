"""
Prompt overlay for expert files.

An expert's system.md and skills are co-located beside its code (the committed
baseline), but their production text can be supplied out of git via the same
overlay folder the registry prompts use. These helpers map an expert file to its
overlay-relative path and resolve overlay-first. (Imports are local to dodge any
package import-order edge.)
"""

from __future__ import annotations

from pathlib import Path


def expert_overlay_rel(module_dir: Path, *parts: str) -> str:
    """Overlay-relative path for an expert file, mirroring its repo layout
    (e.g. experts/web_research/system.md). Falls back to the bare dir name if the
    module somehow sits outside the repo root."""
    from registry.config.prompts import REPO_ROOT

    try:
        rel = module_dir.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = Path(module_dir.name)
    return rel.joinpath(*parts).as_posix()


def overlaid(module_dir: Path, baseline: Path) -> Path:
    """Resolve one expert file (system.md or a skill) through the prompt overlay:
    the production text wins, the committed file is the fallback."""
    from registry.config.prompts import resolve_overlay

    rel = expert_overlay_rel(module_dir, *baseline.relative_to(module_dir).parts)
    path, _source = resolve_overlay(rel, baseline)
    return path
