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

DEFAULT_BATCHES_PATH = get_root() / "batches.yaml"

# Config can tighten a defense, never silently loosen one (D7/D8 discipline):
# a batches.yaml edit alone must not be able to hand a batch egress or elevated
# access. A batch that genuinely needs NETWORK/ELEVATED later is a deliberate,
# reviewed, explicit opt-in (a code change here), never a YAML-only grant.
_FORBIDDEN_GRANTS = frozenset({PermissionLevel.NETWORK, PermissionLevel.ELEVATED})


def _load_batches(path: str | Path) -> dict[str, BatchDefinition]:
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
                grants=grants,
            )
        except KeyError as exc:
            raise ConfigError(f"batch {batch_key!r} is missing required field {exc}") from exc
    return batches


def load_batches(path: str | Path = DEFAULT_BATCHES_PATH) -> dict[str, BatchDefinition]:
    """Convenience loader for wiring.py — cached so hot-path startup doesn't
    re-read batches.yaml on every request. Tests that change batch config at
    runtime should call cache_clear() on this function."""
    return _cached_load_batches(str(Path(path)))


@lru_cache(maxsize=8)
def _cached_load_batches(path: str) -> dict[str, BatchDefinition]:
    return _load_batches(path)
