"""
Prompt registry loaded from the root prompts/ directory, with an optional
deploy-time overlay for keeping production prompt text out of git.

Every LLM-using layer resolves its system/instruction prompts through this
module instead of hardcoding prompt text inline. Prompt *content* lives as
markdown files under prompts/ (one file per prompt); this module is the cached
loader that resolves a prompt by name and carries a version tag for provenance.

The layout mirrors the model registry on purpose:

    prompts/registry.yaml   # name -> {version, file, locked}   (the index)
    prompts/verifier/system.md                                   (the content)

OVERLAY (production prompts, never committed):
    ALL prompts for every LLM call -- the registry prompts here AND each expert's
    co-located system.md + skills -- resolve from a single overlay folder FIRST,
    falling back to the committed file if absent. The overlay is found by, in
    order: (1) VRAKSHA_PROMPTS_DIR if set; (2) an auto-discovered `prompts.secure/`
    folder dropped next to the running agent (CWD) or beside the code (repo root)
    -- zero config, just drop it in; (3) nothing => committed baselines (today's
    behavior; nothing breaks). The overlay mirrors the tree:
    <overlay>/verifier/system.md, <overlay>/experts/<name>/system.md,
    <overlay>/experts/<name>/skills/<s>.md. See overlay_root() / resolve_overlay();
    the expert handler resolves through the same pair.

    VRAKSHA_REQUIRE_PROD_PROMPTS=1 makes boot FAIL CLOSED if any `locked` prompt
    (verifier, filter) is still resolving to its committed baseline -- the guard
    against silently shipping a dev-grade security prompt to production. Unlocked
    prompts (orchestrator, memory, experts) always fall back gracefully.

SECURITY:
  - The manifest (registry.yaml, including every `locked` flag) is ALWAYS read
    from the in-repo prompts/ dir, never the overlay. The overlay supplies only
    file CONTENT for already-declared prompts, so it can never un-lock a prompt
    or introduce a new one.
  - There is NO runtime/end-user override: the overlay is a trusted, operator-set
    deploy path, not request data. Never add a code path that lets runtime data
    or end users replace a prompt's text.
  - `locked` prompts (verifier, output filter) are security boundaries -- the
    verifier is the sole input content blocker; the filter is the output gate.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from foundation import ConfigError, get_root


log = logging.getLogger(__name__)

REPO_ROOT = get_root()
DEFAULT_PROMPTS_DIR = REPO_ROOT / "prompts"
MANIFEST_NAME = "registry.yaml"
OVERLAY_ENV = "VRAKSHA_PROMPTS_DIR"
REQUIRE_PROD_ENV = "VRAKSHA_REQUIRE_PROD_PROMPTS"
PROD_DIRNAME = "prompts.secure"   # auto-discovered drop-in overlay folder
_TRUTHY = {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Overlay resolution — the single place that decides where a prompt's text comes
# from. Shared by the registry prompt loader (below) AND the expert handler, so
# every LLM prompt in the system (registry prompts, expert system.md, skills)
# rides one overlay folder with the same fallback rule.
# ---------------------------------------------------------------------------


def overlay_root() -> Path | None:
    """The active prompt overlay root, or None to use committed baselines.

    Resolution order:
      1. VRAKSHA_PROMPTS_DIR env -- explicit override (lives in .env/.env.local).
      2. Auto-discovered `prompts.secure/` next to where the agent runs (CWD) or
         beside the code (repo root) -- a drop-in folder, zero config.
      3. None -> committed prompts/ baselines.
    """
    env = os.getenv(OVERLAY_ENV)
    if env:
        return Path(env)
    for base in (Path.cwd(), REPO_ROOT):
        candidate = base / PROD_DIRNAME
        if candidate.is_dir():
            return candidate
    return None


def resolve_overlay(overlay_rel: str, baseline: Path) -> tuple[Path, str]:
    """Resolve one prompt file: overlay (prod) first, committed baseline second.

    `overlay_rel` is the file's path inside the overlay folder (POSIX, e.g.
    "verifier/system.md" or "experts/web_research/system.md"). Returns
    (path, source) with source "overlay" or "baseline".
    """
    root = overlay_root()
    if root is not None:
        candidate = root / overlay_rel
        if candidate.is_file():
            return candidate, "overlay"
    return baseline, "baseline"


def read_overlay_text(overlay_rel: str, baseline: Path) -> tuple[str, str]:
    """resolve_overlay() + read the file. Returns (stripped_text, source); raises
    ConfigError if the resolved file is missing or empty."""
    path, source = resolve_overlay(overlay_rel, baseline)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise ConfigError(f"prompt file not found: {path}", cause=exc) from exc
    if not text:
        raise ConfigError(f"prompt file is empty: {path}")
    return text, source


@dataclass(frozen=True, slots=True)
class Prompt:
    """A resolved prompt: its text plus the provenance to trace a verdict."""
    name: str
    version: int
    text: str
    locked: bool = True
    source: str = "baseline"  # "baseline" (committed) or "overlay" (VRAKSHA_PROMPTS_DIR)


class PromptRegistry:
    """
    Reads prompts/registry.yaml and the markdown files it points at.

    All prompt files are read once at load time and held as Prompt objects, so
    get() is a plain dict lookup on the hot path and a missing/broken prompt
    fails fast at load rather than on first use.
    """
    def __init__(self, prompts: dict[str, Prompt]) -> None:
        self.prompts = prompts

    @classmethod
    def from_dir(
        cls,
        base_dir: str | Path = DEFAULT_PROMPTS_DIR,
        *,
        overlay_dir: str | Path | None = None,
        require_overlay_for_locked: bool = False,
    ) -> "PromptRegistry":
        """Load every prompt declared in the manifest under base_dir.

        The manifest (and its `locked` flags) is always read from base_dir. When
        overlay_dir is given, each prompt's *content* is read from there first,
        falling back to base_dir. With require_overlay_for_locked, a `locked`
        prompt that still resolves to its base_dir baseline is a load error.
        """
        base = Path(base_dir)
        overlay = Path(overlay_dir) if overlay_dir else None
        manifest_path = base / MANIFEST_NAME

        try:
            with manifest_path.open("r", encoding="utf-8") as file:
                manifest = yaml.safe_load(file) or {}
        except FileNotFoundError as exc:
            raise ConfigError(f"prompt manifest not found: {manifest_path}", cause=exc) from exc
        except yaml.YAMLError as exc:
            raise ConfigError(f"prompt manifest is not valid YAML: {manifest_path}", cause=exc) from exc

        if not isinstance(manifest, dict):
            raise ConfigError(f"prompt manifest must be a mapping: {manifest_path}")

        prompts = {
            name: cls._load_one(
                str(name), entry, base, overlay, manifest_path, require_overlay_for_locked
            )
            for name, entry in manifest.items()
        }

        if overlay is not None:
            summary = ", ".join(f"{n}<-{p.source}" for n, p in prompts.items())
            log.info("prompt overlay %s active: %s", overlay, summary)

        return cls(prompts)

    @staticmethod
    def _load_one(
        name: str,
        entry: Any,
        base: Path,
        overlay: Path | None,
        manifest_path: Path,
        require_overlay_for_locked: bool,
    ) -> Prompt:
        """Validate one manifest entry and read its prompt file (overlay first)."""
        if not isinstance(entry, dict):
            raise ConfigError(f"prompt {name!r} entry must be a mapping in {manifest_path}")

        relative = entry.get("file")
        if not relative:
            raise ConfigError(f"prompt {name!r} has no 'file' in {manifest_path}")

        version = entry.get("version")
        if not isinstance(version, int):
            raise ConfigError(f"prompt {name!r} needs an integer 'version' in {manifest_path}")

        locked = bool(entry.get("locked", True))

        # Resolve content: overlay (production) first, committed baseline second.
        prompt_path = base / str(relative)
        source = "baseline"
        if overlay is not None:
            candidate = overlay / str(relative)
            if candidate.is_file():
                prompt_path = candidate
                source = "overlay"

        # Fail closed: a security-boundary prompt must not run from the committed
        # baseline when production prompts are required.
        if require_overlay_for_locked and locked and source != "overlay":
            expected = overlay / str(relative) if overlay is not None else f"<{OVERLAY_ENV} unset>"
            raise ConfigError(
                f"prompt {name!r} is locked and {REQUIRE_PROD_ENV} is set, but no overlay "
                f"file was found at {expected}. Refusing to run a locked security prompt "
                f"from its committed baseline in production."
            )

        try:
            text = prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise ConfigError(f"prompt {name!r} file not found: {prompt_path}", cause=exc) from exc

        if not text:
            raise ConfigError(f"prompt {name!r} file is empty: {prompt_path}")

        return Prompt(name=name, version=version, text=text, locked=locked, source=source)

    def get(self, name: str) -> Prompt:
        """Return the prompt registered under name."""
        prompt = self.prompts.get(name)
        if prompt is None:
            raise ConfigError(f"Unknown prompt: {name!r}")
        return prompt


def get_prompt(name: str, base_dir: str | Path = DEFAULT_PROMPTS_DIR) -> Prompt:
    """
    Convenience accessor for stages that just want a prompt by name.

    The registry is cached so hot-path stages do not re-read the prompt files on
    every request. Tests that change prompt files or the overlay env at runtime
    can call load_prompt_registry.cache_clear().
    """
    return load_prompt_registry(base_dir).get(name)


def load_prompt_registry(base_dir: str | Path = DEFAULT_PROMPTS_DIR) -> PromptRegistry:
    """Load (and cache) the prompt registry rooted at base_dir.

    The deploy-time overlay (resolved by overlay_root(): VRAKSHA_PROMPTS_DIR or an
    auto-discovered prompts.secure/) and the fail-closed flag
    (VRAKSHA_REQUIRE_PROD_PROMPTS) are folded into the cache key, so a process with
    a fixed env/layout resolves prompts once.
    """
    root = overlay_root()
    overlay = str(root) if root is not None else None
    require = os.getenv(REQUIRE_PROD_ENV, "").strip().lower() in _TRUTHY
    return _load_prompt_registry(str(Path(base_dir)), overlay, require)


@lru_cache(maxsize=8)
def _load_prompt_registry(
    base_dir: str, overlay_dir: str | None, require_overlay_for_locked: bool
) -> PromptRegistry:
    """Cached implementation behind load_prompt_registry()."""
    return PromptRegistry.from_dir(
        base_dir,
        overlay_dir=overlay_dir,
        require_overlay_for_locked=require_overlay_for_locked,
    )


load_prompt_registry.cache_clear = _load_prompt_registry.cache_clear
