"""
Batch registry loaded from the root batches.yaml file — mirrors models.py's
shape exactly (same fail-closed ConfigError posture, same lru_cache convenience
loader), since batches.yaml is the same category of data: routing/registry
wiring, not an owner-tuned business value (that's config/business.yaml).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from foundation import ConfigError, PermissionLevel, get_root
from registry.capabilities.handler import BatchDefinition
from registry.config.prompts import PromptRegistry, load_prompt_registry

DEFAULT_BATCHES_PATH = get_root() / "batches.yaml"
_BATCH_PROMPT_PREFIX = "batch_orchestrator"

# Config can tighten a defense, never silently loosen one (D7/D8 discipline):
# a batches.yaml edit alone must not be able to hand a batch egress or elevated
# access. A batch that genuinely needs NETWORK/ELEVATED later is a deliberate,
# reviewed, explicit opt-in (a code change here), never a YAML-only grant.
_FORBIDDEN_GRANTS = frozenset({PermissionLevel.NETWORK, PermissionLevel.ELEVATED})


def _batch_prompt_name(batch_key: str) -> str:
    """Every batch owns its own prompt entry -- no shared/default name."""
    return f"{_BATCH_PROMPT_PREFIX}.{batch_key}"


def _read_batch_config(path: str | Path) -> dict:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"batches config not found: {config_path}", cause=exc) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"batches config is not valid YAML: {config_path}", cause=exc) from exc

    if not isinstance(config, dict):
        raise ConfigError(f"batches config must be a mapping: {config_path}")
    return config


def _batch_prompt_text(batch_key: str, prompts: PromptRegistry) -> str:
    """Fails closed: a batch_key with no matching `batch_orchestrator.<batch_key>`
    entry in the prompt registry is a ConfigError, never a fallback to some
    shared/default prompt -- that silent shared default is exactly what
    per-batch prompts replace."""
    name = _batch_prompt_name(batch_key)
    try:
        return prompts.get(name).text
    except ConfigError as exc:
        raise ConfigError(
            f"batch {batch_key!r} has no registered prompt {name!r} -- every "
            "batch needs its own batch_orchestrator.<key> entry in "
            "prompts/registry.yaml, there is no shared default"
        ) from exc


def _resolve_prompt_texts(path: str | Path, prompts: PromptRegistry) -> dict[str, str]:
    """batch_key -> that batch's own prompt text (see `_batch_prompt_text`)."""
    config = _read_batch_config(path)
    return {str(key): _batch_prompt_text(str(key), prompts) for key in config}


def _parse_batches(path: str | Path, *, prompt_texts: dict[str, str]) -> dict[str, BatchDefinition]:
    config = _read_batch_config(path)

    batches: dict[str, BatchDefinition] = {}
    for batch_key, entry in config.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"batch {batch_key!r} entry must be a mapping")
        try:
            grants = frozenset(PermissionLevel(str(g)) for g in entry.get("grants", []))
        except ValueError as exc:
            raise ConfigError(f"batch {batch_key!r} has an invalid grant: {exc}") from exc
        escalated = grants & _FORBIDDEN_GRANTS
        if escalated:
            names = ", ".join(sorted(g.value for g in escalated))
            raise ConfigError(
                f"batch {batch_key!r} requests forbidden grant(s) {{{names}}} — "
                "NETWORK/ELEVATED cannot be granted via batches.yaml alone; "
                "that requires a deliberate, reviewed code change"
            )
        try:
            batches[str(batch_key)] = BatchDefinition(
                domain=str(entry["domain"]),
                expert_keys=frozenset(str(k) for k in entry.get("expert_keys", [])),
                tool_keys=frozenset(str(k) for k in entry.get("tool_keys", [])),
                system_prompt=prompt_texts[str(batch_key)],
                grants=grants,
                grants_graph=bool(entry.get("grants_graph", False)),
            )
        except KeyError as exc:
            raise ConfigError(f"batch {batch_key!r} is missing required field {exc}") from exc
    return batches


def _load_batches(
    path: str | Path,
    *,
    prompt_registry: PromptRegistry | None = None,
) -> dict[str, BatchDefinition]:
    """Load batch definitions, each with its OWN overlay-resolved prompt.

    `prompt_registry` is injectable for hermetic tests. Production uses the
    same cached PromptRegistry as every other LLM layer, so the trusted prompt
    overlay applies to batches without a second resolution path.
    """
    prompts = prompt_registry or load_prompt_registry()
    prompt_texts = _resolve_prompt_texts(path, prompts)
    return _parse_batches(path, prompt_texts=prompt_texts)


def load_batches(path: str | Path = DEFAULT_BATCHES_PATH) -> dict[str, BatchDefinition]:
    """Convenience loader for wiring.py — cached so hot-path startup doesn't
    re-read batches.yaml on every request. Tests that change batch config at
    runtime should call cache_clear() on this function (and on
    `_cached_batch_keys` if the set of batch_keys itself changed)."""
    path_str = str(Path(path))
    prompts = load_prompt_registry()
    batch_keys = _cached_batch_keys(path_str)
    prompt_texts = tuple(sorted((key, _batch_prompt_text(key, prompts)) for key in batch_keys))
    return _cached_load_batches(path_str, prompt_texts)


@lru_cache(maxsize=8)
def _cached_batch_keys(path: str) -> tuple[str, ...]:
    """The set of batch_keys in batches.yaml, cached by path so the hot path
    doesn't re-read the file every request -- only the (cheap, in-memory)
    per-batch prompt lookup runs on every call."""
    return tuple(str(key) for key in _read_batch_config(path))


@lru_cache(maxsize=8)
def _cached_load_batches(
    path: str, prompt_texts: tuple[tuple[str, str], ...]
) -> dict[str, BatchDefinition]:
    # Each batch's own prompt text is part of the cache key (not just its
    # batch_key), so an operator-selected overlay can never inherit a
    # BatchDefinition cached from another batch's or baseline's content, and
    # two batches with different prompts never collide on one cache entry.
    return _parse_batches(path, prompt_texts=dict(prompt_texts))
