"""
Prompt registry loaded from the root prompts/ directory.

Every LLM-using layer should resolve its system/instruction prompts through this
module instead of hardcoding prompt text inline. Prompt *content* lives as
markdown files under prompts/ (one file per prompt); this module is the cached
loader that resolves a prompt by name and carries a version tag for provenance.

The layout mirrors the model registry on purpose:

    prompts/registry.yaml   # name -> {version, file, locked}   (the index)
    prompts/verifier/system.md                                   (the content)

SECURITY: each prompt carries a `locked` flag. Locked prompts (verifier, output
filter) are security boundaries — the verifier prompt is the sole input content
blocker. This loader deliberately exposes NO override mechanism: it only reads
the on-disk, version-controlled prompt. Never add a code path that lets runtime
data or end users replace a locked prompt's text.

TODO(orchestrator): when the orchestrator/experts/output-filter land, extend
this with:
  - a render(**vars) step for prompts that inject runtime context (memory,
    available tools, persona) — keep it simple string substitution until a real
    need forces a template engine.
  - customizable (locked: false) prompts sourced per-user/per-tier from config
    or the DB. Locked prompts MUST stay on this read-only path regardless.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from foundation import ConfigError


DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
MANIFEST_NAME = "registry.yaml"


@dataclass(frozen=True, slots=True)
class Prompt:
    """A resolved prompt: its text plus the provenance to trace a verdict."""
    name: str
    version: int
    text: str
    locked: bool = True


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
    def from_dir(cls, base_dir: str | Path = DEFAULT_PROMPTS_DIR) -> "PromptRegistry":
        """Load every prompt declared in the manifest under base_dir."""
        base = Path(base_dir)
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
            name: cls._load_one(str(name), entry, base, manifest_path)
            for name, entry in manifest.items()
        }
        return cls(prompts)

    @staticmethod
    def _load_one(
        name: str,
        entry: Any,
        base: Path,
        manifest_path: Path,
    ) -> Prompt:
        """Validate one manifest entry and read its prompt file."""
        if not isinstance(entry, dict):
            raise ConfigError(f"prompt {name!r} entry must be a mapping in {manifest_path}")

        relative = entry.get("file")
        if not relative:
            raise ConfigError(f"prompt {name!r} has no 'file' in {manifest_path}")

        version = entry.get("version")
        if not isinstance(version, int):
            raise ConfigError(f"prompt {name!r} needs an integer 'version' in {manifest_path}")

        prompt_path = base / str(relative)
        try:
            text = prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise ConfigError(f"prompt {name!r} file not found: {prompt_path}", cause=exc) from exc

        if not text:
            raise ConfigError(f"prompt {name!r} file is empty: {prompt_path}")

        return Prompt(
            name=name,
            version=version,
            text=text,
            locked=bool(entry.get("locked", True)),
        )

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
    every request. Tests that change prompt files at runtime can call
    load_prompt_registry.cache_clear().
    """
    return load_prompt_registry(base_dir).get(name)


def load_prompt_registry(base_dir: str | Path = DEFAULT_PROMPTS_DIR) -> PromptRegistry:
    """Load (and cache) the prompt registry rooted at base_dir."""
    return _load_prompt_registry(str(Path(base_dir)))


@lru_cache(maxsize=8)
def _load_prompt_registry(base_dir: str) -> PromptRegistry:
    """Cached implementation behind load_prompt_registry()."""
    return PromptRegistry.from_dir(base_dir)


load_prompt_registry.cache_clear = _load_prompt_registry.cache_clear
