"""
Hermetic characterization harness: image/audio/video media-dispatch in
normalize_payload() (core/normalizer/builders.py).

Pins the two dispatch branches for each of image, audio, video:
  (a) supports=True  -> _preserve_native  (preserved_native=True, native_payload
                        is the original bytes, content empty, requires_expert=False)
  (b) supports=False -> _requires_expert  (requires_expert=True,
                        required_capability == modality, native_payload preserved,
                        preserved_native=False)

Scope fences:
- Always passes an explicit target_layer + a monkeypatched registry double so
  the test is independent of the gated #17 capability-resolution path (the test
  pins the supports->dispatch MECHANISM given a model, never the normalizer
  stage's default-layer choice).
- Additive only: does NOT edit builders.py / foundation/contracts/payloads.py /
  the registry / any constant.
- No real model load, no network, no paid keys.
- Does NOT re-pin the existing text/PDF/scanned-PDF cases (tests/normalizer.py).

On divergence: if any assertion fails the test reports a VIOLATED verdict in the
per-modality table. Do not edit builders.py; file a needs-reviewer note instead.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.normalizer import builders

_SENTINEL = b"<media-payload>"

_MEDIA_MODALITIES = ["image", "audio", "video"]

_TARGET_LAYER = "orchestrator"


def _registry_double(supports_result: bool) -> MagicMock:
    """
    Return a minimal registry double whose for_layer(...).supports(...) returns
    a controlled bool. provider + model fields satisfy the post-dispatch
    target_provider / target_model assignments in normalize_payload.
    """
    profile = MagicMock()
    profile.supports.return_value = supports_result
    profile.provider = "stub-provider"
    profile.model = "stub-model"
    registry = MagicMock()
    registry.for_layer.return_value = profile
    return registry


@pytest.mark.parametrize("modality", _MEDIA_MODALITIES)
def test_supported_media_is_preserved_native(monkeypatch, modality):
    """
    supports=True -> _preserve_native:
      preserved_native=True, native_payload is original bytes,
      content empty, requires_expert=False.
    """
    monkeypatch.setattr(
        builders,
        "load_model_registry",
        lambda: _registry_double(True),
    )

    ni = builders.normalize_payload(
        _SENTINEL, modality=modality, target_layer=_TARGET_LAYER
    )

    assert ni.preserved_native is True, (
        f"[{modality}] supports=True: expected preserved_native=True, got {ni.preserved_native}"
    )
    assert ni.native_payload is _SENTINEL, (
        f"[{modality}] supports=True: expected native_payload to be the original bytes object"
    )
    assert not ni.content, (
        f"[{modality}] supports=True: expected content empty, got {ni.content!r}"
    )
    assert ni.requires_expert is False, (
        f"[{modality}] supports=True: expected requires_expert=False, got {ni.requires_expert}"
    )


@pytest.mark.parametrize("modality", _MEDIA_MODALITIES)
def test_unsupported_media_routes_to_expert(monkeypatch, modality):
    """
    supports=False -> _requires_expert:
      requires_expert=True, required_capability==modality,
      native_payload preserved, preserved_native=False.
    """
    monkeypatch.setattr(
        builders,
        "load_model_registry",
        lambda: _registry_double(False),
    )

    ni = builders.normalize_payload(
        _SENTINEL, modality=modality, target_layer=_TARGET_LAYER
    )

    assert ni.requires_expert is True, (
        f"[{modality}] supports=False: expected requires_expert=True, got {ni.requires_expert}"
    )
    assert ni.required_capability == modality, (
        f"[{modality}] supports=False: expected required_capability=={modality!r}, "
        f"got {ni.required_capability!r}"
    )
    assert ni.native_payload is _SENTINEL, (
        f"[{modality}] supports=False: expected native_payload preserved for downstream expert"
    )
    assert ni.preserved_native is False, (
        f"[{modality}] supports=False: expected preserved_native=False, got {ni.preserved_native}"
    )


def test_media_dispatch_summary(monkeypatch):
    """
    Collect both branches for all three modalities and print a dispatch table.

    Verdict column:
      HELD     - dispatch matches the documented contract
      VIOLATED - dispatch diverges; open a needs-reviewer note, do not edit builders.py

    The test fails (and reports VIOLATED rows) if any branch diverges.
    """
    rows: list[tuple[str, str, str]] = []
    violations: list[str] = []

    for modality in _MEDIA_MODALITIES:
        monkeypatch.setattr(
            builders,
            "load_model_registry",
            lambda: _registry_double(True),
        )
        ni_sup = builders.normalize_payload(
            _SENTINEL, modality=modality, target_layer=_TARGET_LAYER
        )
        sup_ok = (
            ni_sup.preserved_native is True
            and ni_sup.native_payload is _SENTINEL
            and not ni_sup.content
            and ni_sup.requires_expert is False
        )

        monkeypatch.setattr(
            builders,
            "load_model_registry",
            lambda: _registry_double(False),
        )
        ni_unsup = builders.normalize_payload(
            _SENTINEL, modality=modality, target_layer=_TARGET_LAYER
        )
        unsup_ok = (
            ni_unsup.requires_expert is True
            and ni_unsup.required_capability == modality
            and ni_unsup.native_payload is _SENTINEL
            and ni_unsup.preserved_native is False
        )

        v_sup = "HELD" if sup_ok else "VIOLATED"
        v_unsup = "HELD" if unsup_ok else "VIOLATED"
        rows.append((modality, v_sup, v_unsup))
        if not sup_ok:
            violations.append(f"{modality}/supports=True -> expected PRESERVED-NATIVE")
        if not unsup_ok:
            violations.append(f"{modality}/supports=False -> expected ROUTED-TO-EXPERT")

    _print_dispatch_table(rows)

    assert not violations, (
        "media-dispatch VIOLATED for:\n  "
        + "\n  ".join(violations)
        + "\nThis is a real gap. Open a needs-reviewer note; do NOT edit builders.py."
    )


def _print_dispatch_table(rows: list[tuple[str, str, str]]) -> None:
    all_held = all(vs == "HELD" and vu == "HELD" for _, vs, vu in rows)
    overall = "media-dispatch held" if all_held else "media-dispatch VIOLATED"

    print()
    print("=== normalizer media-dispatch characterization ===")
    print(f"  {'modality':<8}  {'supports=True (PRESERVED-NATIVE)':^34}  {'supports=False (ROUTED-TO-EXPERT)':^34}")
    print(f"  {'-'*8}  {'-'*34}  {'-'*34}")
    for modality, v_sup, v_unsup in rows:
        print(f"  {modality:<8}  {v_sup:^34}  {v_unsup:^34}")
    print(f"  {'-'*8}  {'-'*34}  {'-'*34}")
    print(f"  Overall: {overall}")
    print("===================================================")
