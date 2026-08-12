"""Canonical runtime-environment interpretation shared across backend layers."""

from __future__ import annotations

import os
from enum import Enum


class RuntimeEnvironment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class RuntimeEnvironmentError(RuntimeError):
    """Environment selection is invalid or contradictory."""


_ALIASES = {
    "dev": RuntimeEnvironment.DEVELOPMENT,
    "development": RuntimeEnvironment.DEVELOPMENT,
    "test": RuntimeEnvironment.TEST,
    "testing": RuntimeEnvironment.TEST,
    "prod": RuntimeEnvironment.PRODUCTION,
    "production": RuntimeEnvironment.PRODUCTION,
}


def _parse(name: str, raw: str) -> RuntimeEnvironment:
    value = raw.strip().lower()
    try:
        return _ALIASES[value]
    except KeyError as exc:
        allowed = ", ".join(sorted(_ALIASES))
        raise RuntimeEnvironmentError(
            f"{name} has unsupported value {raw!r}; expected one of: {allowed}"
        ) from exc


def runtime_environment() -> RuntimeEnvironment:
    """Return one backend-wide mode, with explicit legacy compatibility.

    ``CLANNON_ENV`` is authoritative. ``VRAKSHA_ENV`` remains a migration alias
    only when the canonical variable is absent or agrees exactly. Contradictory
    settings fail closed instead of letting security controls select different modes.
    """

    canonical_raw = (os.getenv("CLANNON_ENV") or "").strip()
    legacy_raw = (os.getenv("VRAKSHA_ENV") or "").strip()

    canonical = _parse("CLANNON_ENV", canonical_raw) if canonical_raw else None
    legacy = _parse("VRAKSHA_ENV", legacy_raw) if legacy_raw else None
    if canonical is not None and legacy is not None and canonical is not legacy:
        raise RuntimeEnvironmentError(
            "CLANNON_ENV and legacy VRAKSHA_ENV select contradictory runtime modes"
        )
    return canonical or legacy or RuntimeEnvironment.DEVELOPMENT


def is_production() -> bool:
    """Whether canonical backend runtime mode is production."""

    return runtime_environment() is RuntimeEnvironment.PRODUCTION
