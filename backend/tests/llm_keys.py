"""Multi-account Google key rotation: each key becomes its own fallback entry,
so one account's quota exhaustion rotates instead of failing the run."""

from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel

from core.llm import registry as reg


def _only_google_keys(monkeypatch, *keys):
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for n in range(2, 10):
        monkeypatch.delenv(f"GOOGLE_API_KEY_{n}", raising=False)
    if keys:
        monkeypatch.setenv("GOOGLE_API_KEY", keys[0])
        for i, key in enumerate(keys[1:], start=2):
            monkeypatch.setenv(f"GOOGLE_API_KEY_{i}", key)


def test_google_keys_collected_in_order(monkeypatch):
    _only_google_keys(monkeypatch, "k1", "k2", "k3")
    assert reg._google_api_keys() == ["k1", "k2", "k3"]


def test_numbering_gap_stops_the_scan(monkeypatch):
    _only_google_keys(monkeypatch, "k1", "k2")
    monkeypatch.setenv("GOOGLE_API_KEY_4", "orphan")  # _3 missing — _4 ignored
    assert reg._google_api_keys() == ["k1", "k2"]


def test_numbered_key_alone_keeps_provider_available(monkeypatch):
    _only_google_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY_2", "k2")
    assert reg._google_api_keys() == ["k2"]
    assert reg._provider_available("google:gemini-2.5-flash") is True


def test_search_chain_expands_per_key(monkeypatch):
    _only_google_keys(monkeypatch, "k1", "k2", "k3")
    model = reg.model_for_layer("search")
    # primary gemini-2.5-flash x3 keys + chain gemini-3.5-flash x3 keys
    # (anthropic last resort dropped: no key in this env)
    assert isinstance(model, FallbackModel)
    assert len(model.models) == 6
    assert all(isinstance(m, GoogleModel) for m in model.models)


def test_single_key_stays_plain(monkeypatch):
    _only_google_keys(monkeypatch, "k1")
    model = reg.model_for_layer("search")
    # no per-key expansion with one key — plain chain entries, inferred lazily
    assert isinstance(model, FallbackModel)
    assert len(model.models) == 2


def test_resolved_models_are_cached_not_rebuilt(monkeypatch):
    _only_google_keys(monkeypatch, "k1", "k2", "k3")
    first = reg.model_for_layer("search")
    second = reg.model_for_layer("search")
    # same object — providers (and their HTTP clients) are not rebuilt per call
    assert first is second
    monkeypatch.setenv("GOOGLE_API_KEY_4", "k4")
    assert reg.model_for_layer("search") is not first  # env change = new resolution
