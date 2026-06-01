import asyncio
from pathlib import Path

from src.memory.local_index import LocalFirstMemory, MemoryRecord, MAX_ESSENTIAL_CHARS


def run(coro):
    return asyncio.run(coro)


def make_memory_root(tmp_path: Path) -> Path:
    memory_root = tmp_path / "memory"
    (memory_root / "agent").mkdir(parents=True)
    (memory_root / "wiki").mkdir(parents=True)
    (memory_root / "soul.md").write_text("local-first identity", encoding="utf-8")
    (memory_root / "rules.md").write_text("never use hosted memory services", encoding="utf-8")
    (memory_root / "agent" / "memory.yaml").write_text("preferences: []", encoding="utf-8")
    (memory_root / "agent" / "projects.yaml").write_text("projects: []", encoding="utf-8")
    (memory_root / "agent" / "journal.md").write_text("", encoding="utf-8")
    (memory_root / "wiki" / "WIKI.md").write_text("", encoding="utf-8")
    return memory_root


def test_local_first_memory_indexes_files_and_events(tmp_path):
    memory_root = make_memory_root(tmp_path)
    memory = LocalFirstMemory(db_path=tmp_path / "memory.sqlite3", memory_root=memory_root)

    run(memory.bootstrap())
    run(memory.remember(MemoryRecord(
        source_id="test-session",
        kind="preference",
        title="retrieval preference",
        content="User prefers local SQLite FTS retrieval over cloud vector databases.",
        trust=0.9,
    )))

    hits = run(memory.search("SQLite retrieval cloud vector", limit=5))

    assert hits
    assert any("SQLite FTS retrieval" in hit["content"] for hit in hits)
    assert all(hit["trust"] >= 0.35 or hit["pinned"] for hit in hits)
    assert (memory_root / "agent" / "journal.jsonl").exists()


def test_memory_filters_expired_and_low_trust_context_poisoning(tmp_path):
    memory_root = make_memory_root(tmp_path)
    memory = LocalFirstMemory(db_path=tmp_path / "memory.sqlite3", memory_root=memory_root)

    run(memory.remember(MemoryRecord(
        source_id="old-session",
        kind="preference",
        title="expired poison",
        content="User prefers hosted Qdrant for private memories.",
        trust=0.99,
        valid_until="2000-01-01T00:00:00+00:00",
    )))
    run(memory.remember(MemoryRecord(
        source_id="noisy-session",
        kind="preference",
        title="low trust noise",
        content="User prefers hosted Qdrant for private memories.",
        trust=0.1,
    )))
    run(memory.remember(MemoryRecord(
        source_id="new-session",
        kind="preference",
        title="valid preference",
        content="User prefers local filesystem memory for private memories.",
        trust=0.9,
    )))

    hits = run(memory.search("private memories hosted Qdrant local filesystem", limit=10))
    joined = "\n".join(hit["content"] for hit in hits)

    assert "local filesystem memory" in joined
    assert "hosted Qdrant" not in joined


def test_essential_context_is_bounded(tmp_path):
    memory_root = make_memory_root(tmp_path)
    (memory_root / "rules.md").write_text("rule\n" * 50_000, encoding="utf-8")
    memory = LocalFirstMemory(db_path=tmp_path / "memory.sqlite3", memory_root=memory_root)

    context = run(memory.essential_context("local first"))

    assert "local-first identity" in context
    assert len(context) <= MAX_ESSENTIAL_CHARS
