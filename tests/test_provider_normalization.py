from src.utils.api_key_utils import (
    ApiKeyStore,
    PROVIDER_KEY_SCHEMA,
    normalize_provider_name,
)


def test_provider_names_normalize_to_canonical_keys():
    assert normalize_provider_name("claude") == "anthropic"
    assert normalize_provider_name("chatgpt") == "openai"
    assert normalize_provider_name("gemini") == "google"
    assert normalize_provider_name("hugging-face") == "huggingface"


def test_api_key_store_accepts_alias_env_names(monkeypatch):
    for env_vars in PROVIDER_KEY_SCHEMA.values():
        for env_var in env_vars:
            monkeypatch.delenv(env_var, raising=False)

    monkeypatch.setenv("CLAUDE_API_KEY", "anthropic-key")
    monkeypatch.setenv("CHATGPT_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "google-key")

    store = ApiKeyStore(PROVIDER_KEY_SCHEMA)
    store.load_keys()

    assert store.get_key("anthropic") == "anthropic-key"
    assert store.get_key("claude") == "anthropic-key"
    assert store.get_key("openai") == "openai-key"
    assert store.get_key("chatgpt") == "openai-key"
    assert store.get_key("google") == "google-key"
    assert store.get_key("gemini") == "google-key"
