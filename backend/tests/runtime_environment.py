"""Hermetic contract tests for canonical backend runtime mode."""

from __future__ import annotations

import pytest

from foundation import (
    RuntimeEnvironment,
    RuntimeEnvironmentError,
    is_production,
    runtime_environment,
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLANNON_ENV", raising=False)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)


def test_unset_defaults_to_development(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    assert runtime_environment() is RuntimeEnvironment.DEVELOPMENT
    assert not is_production()


@pytest.mark.parametrize("value", ["prod", "production", " PRODUCTION "])
def test_canonical_production_aliases(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CLANNON_ENV", value)
    assert is_production()


def test_legacy_only_remains_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VRAKSHA_ENV", "production")
    assert is_production()


def test_matching_canonical_and_legacy_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CLANNON_ENV", "prod")
    monkeypatch.setenv("VRAKSHA_ENV", "production")
    assert is_production()


def test_contradictory_canonical_and_legacy_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CLANNON_ENV", "production")
    monkeypatch.setenv("VRAKSHA_ENV", "development")
    with pytest.raises(RuntimeEnvironmentError, match="contradictory"):
        runtime_environment()


@pytest.mark.parametrize("name", ["CLANNON_ENV", "VRAKSHA_ENV"])
def test_unknown_mode_never_silently_becomes_development(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv(name, "prodution")
    with pytest.raises(RuntimeEnvironmentError, match="unsupported"):
        runtime_environment()
