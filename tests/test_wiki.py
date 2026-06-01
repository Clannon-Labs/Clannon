from src.memory import wiki


def test_load_wiki_returns_core_memory_context(tmp_path, monkeypatch):
    memory_root = tmp_path / "memory"
    wiki_path = memory_root / "wiki"
    wiki_path.mkdir(parents=True)
    (memory_root / "soul.md").write_text("local-first identity", encoding="utf-8")
    (memory_root / "rules.md").write_text("keep tests deterministic", encoding="utf-8")
    (wiki_path / "rules.md").write_text("wiki rule", encoding="utf-8")

    monkeypatch.setattr(wiki, "MEMORY_ROOT", memory_root)
    monkeypatch.setattr(wiki, "WIKI_PATH", wiki_path)

    content = wiki.load_wiki()

    assert "local-first identity" in content
    assert "keep tests deterministic" in content
    assert "wiki rule" in content
