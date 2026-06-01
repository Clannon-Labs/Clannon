"""
Local-First Persistent Memory Layer for Vraksha.

This module provides a hybrid storage solution combining:
1. Raw Filesystem Logs (Durable & Immutable)
2. SQLite FTS5 Index (High-Performance Keyword Retrieval)
3. In-Memory Hot Cache (Zero-Latency Short-Term Recall)

Architecture:
- I/O: Asynchronous background writes for non-critical logs.
- Retrieval: Diversified BM25 ranking with trust-based gating.
- Scalability: Streaming chunking for large file indexing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from get_root import root
from src.memory.utils.async_journal_writer import AsyncJournalWriter

logger = logging.getLogger(__name__)

MEMORY_ROOT = root.project / "memory"
INDEX_DB = MEMORY_ROOT / "index" / "memory.sqlite3"
MAX_FILE_BYTES = 64 * 1024 # 64 KB  
MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP = 180
MAX_ESSENTIAL_CHARS = 18_000
MAX_HOT_CACHE = 16
MAX_RESULTS = 8
TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


# Global singleton for background logging
_journal_writer = AsyncJournalWriter()


def bounded_read_text(path: Path, max_bytes: int = MAX_FILE_BYTES) -> str:
    """Read a text file with a hard cap to protect the LLM context window.
    
    Modern LLMs have expansive windows, but their 'attention' density drops 
    significantly as the prompt grows (the 'Lost in the Middle' problem). 
    Feeding 1MB of raw logs into a prompt is often counter-productive. 
    
    This helper caps the read at 64KB (``MAX_FILE_BYTES``). This ensures that 
    the agent remains focused on the task while having enough recent context 
    to be effective. For deeper history, the agent should rely on the 
    indexed search via :meth:`LocalFirstMemory.search`.
    """
    raw = path.read_bytes()[:max_bytes]
    text = raw.decode("utf-8", errors="replace")

    if path.stat().st_size > max_bytes:
        text += "\n...[truncated: indexed search holds the full file]"

    return text


def chunk_text_stream(path: Path, size: int = MAX_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> Iterable[tuple[int, str]]:
    """Stream-chunk a file from disk to avoid memory spikes and context loss.
    
    Loading a multi-GB repository file into a single string to chunk it in memory 
    is a common cause of OOM (Out of Memory) crashes. This generator streams 
    the file in small increments and breaks it into overlapping chunks.
    
    The generator scans for 'semantic break points' (double-newlines or sentence 
    ends) to keep related logic together. Crucially, it maintains a 180-character 
    overlap between chunks. This overlap ensures that if a critical fact (like 
    a function signature) is split at the chunk boundary, both chunks retain 
    enough surrounding text for the LLM to reconstruct the full meaning.
    """
    idx = 0
    buffer = ""

    with path.open("r", encoding="utf-8", errors="replace") as f:
        while True:
            chunk = f.read(size * 4) # Read ahead buffer

            if not chunk:
                break

            buffer += chunk

            while len(buffer) > size:
                # We prioritize double-newlines and sentence ends to keep 
                # related thoughts together within a single chunk.
                boundary = max(buffer.rfind("\n\n", 0, size), buffer.rfind(". ", 0, size))
                end = boundary + 1 if boundary > size // 2 else size
                
                yield idx, buffer[:end].strip()
                buffer = buffer[end - overlap:]
                idx += 1

        if buffer.strip():
            yield idx, buffer.strip()


@dataclass(slots=True)
class MemoryRecord:
    """A unified data structure for facts, rules, and events across all stores.
    
    Vraksha uses a Tri-Store approach (Wiki, Semantic, SQLite), but the 
    retrieval engine expects a single, predictable contract. This record 
    normalizes external Markdown files and internal SQLite rows. 
    
    The use of ``slots=True`` is a deliberate optimization to reduce the memory 
    footprint of the 'Hot Cache' when thousands of records are held in RAM.
    """
    source_id: str
    kind: str           # e.g., 'fact', 'rule', 'preference', 'episode'
    title: str
    content: str
    trust: float = 0.55 # 0.0 to 1.0; used for retrieval gating
    pinned: bool = False # If true, ignores trust and always stays in context
    valid_until: str | None = None # ISO timestamp for ephemeral facts
    metadata: dict[str, Any] | None = None


class LocalFirstMemory:
    """The core indexing and search engine for Vraksha's long-term memory.
    
    We rely on :mod:`sqlite3`'s FTS5 (Full Text Search) module with BM25 
    ranking for two primary reasons:
    
    1. **Technical Precision**: In software engineering, 'Keyword' matching 
       is often superior to 'Semantic' vector search. If you search for 
       ``MemoryCoordinator``, a vector DB might return ``SemanticLayer`` 
       because they sound conceptually similar, whereas FTS5 will find the 
       actual class definition with 100% precision.
    2. **Zero-Latency Privacy**: Local search is sub-millisecond and 
       requires no external API calls, ensuring your codebase never leaks 
       to third-party vector providers for 'indexing'.
       
    The class implements a 'Hot Cache' for the current session and a 
    persistent SQLite index for multi-session recall.
    """

    def __init__(self, db_path: Path = INDEX_DB, memory_root: Path = MEMORY_ROOT) -> None:
        self.db_path = Path(db_path)
        self.memory_root = Path(memory_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        # RLock allows the same thread to acquire the lock multiple times, 
        # which is necessary for complex recursive indexing tasks.
        self._lock = threading.RLock()
        self._hot_cache: list[MemoryRecord] = [] # Temporary RAM storage for current session
        
        # check_same_thread=False keeps the connection usable from callers that
        # still wrap memory operations in their own worker threads.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._ensure_schema()

    def _configure(self) -> None:
        """Apply performance and concurrency tunings to the SQLite connection.
        
        We use ``journal_mode=WAL`` (Write-Ahead Logging) to ensure that the 
        background consolidation agent can commit new memories without 
        blocking search queries from the main agent loop.
        
        The ``mmap_size`` is set to 256MB to tell the kernel to map the index 
        file directly into address space, effectively turning disk searches 
        into memory-speed lookups.
        """
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=268435456") # 256MB mmap for high-speed indexing
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _ensure_schema(self) -> None:
        """Bootstrap the relational tables and FTS5 virtual index.
        
        FTS5 implements an inverted index using BM25 scoring—the same tech 
        behind high-end search engines, but in a local file.
        """
        with self._lock:
            self._conn.executescript(
                """
                -- Primary document storage
                CREATE TABLE IF NOT EXISTS documents (
                  id INTEGER PRIMARY KEY,
                  doc_key TEXT NOT NULL UNIQUE,
                  source_id TEXT NOT NULL,
                  source_path TEXT,
                  kind TEXT NOT NULL,
                  title TEXT NOT NULL,
                  chunk_index INTEGER NOT NULL DEFAULT 0,
                  content TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  trust REAL NOT NULL DEFAULT 0.55,
                  pinned INTEGER NOT NULL DEFAULT 0,
                  valid_until TEXT,
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  access_count INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                -- Virtual table for lightning-fast keyword search (BM25 ranking)
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                  title, content, kind, source_id,
                  content='documents', content_rowid='id',
                  tokenize='unicode61 remove_diacritics 2'
                );

                -- Triggers automate the mirroring of data into the virtual 
                -- FTS table, keeping the index 100% in sync without extra 
                -- code logic in the Python layer.
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                  INSERT INTO documents_fts(rowid, title, content, kind, source_id)
                  VALUES (new.id, new.title, new.content, new.kind, new.source_id);
                END;
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                  INSERT INTO documents_fts(documents_fts, rowid, title, content, kind, source_id)
                  VALUES('delete', old.id, old.title, old.content, old.kind, old.source_id);
                END;
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                  INSERT INTO documents_fts(documents_fts, rowid, title, content, kind, source_id)
                  VALUES('delete', old.id, old.title, old.content, old.kind, old.source_id);
                  INSERT INTO documents_fts(rowid, title, content, kind, source_id)
                  VALUES (new.id, new.title, new.content, new.kind, new.source_id);
                END;

                CREATE TABLE IF NOT EXISTS source_state (
                  source_path TEXT PRIMARY KEY,
                  mtime_ns INTEGER NOT NULL,
                  size_bytes INTEGER NOT NULL,
                  indexed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_documents_gate
                  ON documents(kind, pinned, trust, valid_until, updated_at);
                CREATE INDEX IF NOT EXISTS idx_documents_source
                  ON documents(source_id, source_path, chunk_index);
                """
            )
            self._conn.commit()

    def core_files(self) -> list[tuple[Path, str, float, bool]]:
        """Defines the 'Ground Truth' files that must always be indexed."""
        return [
            (self.memory_root / "soul.md", "core", 0.99, True),
            (self.memory_root / "rules.md", "core", 0.99, True),
            (self.memory_root / "wiki" / "rules.md", "wiki", 0.90, True),
            (self.memory_root / "agent" / "journal.jsonl", "episode", 0.20, False),
        ]

    async def bootstrap(self) -> None:
        """Initializes the memory layer by re-indexing core files."""
        for path, kind, trust, pinned in self.core_files():
            if path.exists():
                await self.index_file(path, kind=kind, trust=trust, pinned=pinned)

    def bootstrap_sync(self) -> None:
        """Synchronous version of bootstrap."""
        for path, kind, trust, pinned in self.core_files():
            if path.exists():
                self._index_file_sync(path, kind, trust, pinned)

    async def index_file(self, path: Path, *, kind: str, trust: float, pinned: bool = False) -> None:
        """Asynchronously indexes a file on disk."""
        self._index_file_sync(Path(path), kind, trust, pinned)

    def _index_file_sync(self, path: Path, kind: str, trust: float, pinned: bool) -> None:
        """Checks mtime/size to see if the file has changed.
        
        If it has, it deletes old chunks and streams new ones into SQLite. We 
        track mtime and size as a 'fingerprint' to save CPU cycles and I/O.
        """
        stat = path.stat()
        with self._lock:
            state = self._conn.execute(
                "SELECT mtime_ns, size_bytes FROM source_state WHERE source_path = ?", (path.as_posix(),)
            ).fetchone()

        if state and int(state["mtime_ns"]) == stat.st_mtime_ns and int(state["size_bytes"]) == stat.st_size:
            return

        now = utc_now()
        rel = path.as_posix()

        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute("DELETE FROM documents WHERE source_path = ?", (path.as_posix(),))
                for idx, chunk in chunk_text_stream(path):
                    self._insert_record(
                        doc_key=f"file:{path.as_posix()}:{idx}",
                        source_id=rel,
                        source_path=path.as_posix(),
                        kind=kind,
                        title=path.name,
                        chunk_index=idx,
                        content=chunk,
                        trust=trust,
                        pinned=pinned,
                        now=now,
                        metadata={"bytes": stat.st_size}
                    )
                self._conn.execute(
                    "INSERT OR REPLACE INTO source_state(source_path, mtime_ns, size_bytes, indexed_at) VALUES (?, ?, ?, ?)",
                    (path.as_posix(), stat.st_mtime_ns, stat.st_size, now),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    async def remember_many(self, records: list[MemoryRecord]) -> None:
        """Asynchronously persists multiple memory records."""
        self.remember_many_sync(records)

    async def remember(self, record: MemoryRecord) -> None:
        """Persist a single memory record."""
        self.remember_many_sync([record])

    def remember_many_sync(self, records: list[MemoryRecord]) -> None:
        """Commit a batch of memories to all three storage paths.
        
        Every 'memory' event follows three paths for maximum resilience:
        1. **Hot Cache**: Immediate RAM storage for zero-latency context.
        2. **SQLite**: Indexed search storage for multi-session recall.
        3. **Journal**: Durable JSONL append for 'black box' logging.
        
        This multi-path commitment ensures that the agent always has access 
        to the most recent facts while maintaining a durable archive that 
        can be re-indexed if the database is ever lost.
        """
        now = utc_now()

        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")

            try:
                for record in records:
                    self._hot_cache.append(record)
                    # Inline helper for chunking string content
                    start = 0
                    idx = 0

                    while start < len(record.content):
                        end = min(len(record.content), start + MAX_CHUNK_CHARS)
                        chunk = record.content[start:end].strip()

                        if chunk:
                            self._insert_record(
                                doc_key=f"event:{record.source_id}:{sha256_text(record.content)}:{idx}",
                                source_id=record.source_id,
                                source_path=None,
                                kind=record.kind,
                                title=record.title,
                                chunk_index=idx,
                                content=chunk,
                                trust=record.trust,
                                pinned=record.pinned,
                                valid_until=record.valid_until,
                                metadata=record.metadata or {},
                                now=now,
                            )
                            idx += 1

                        start = max(0, end - CHUNK_OVERLAP) if end < len(record.content) else len(record.content)
                    
                    _journal_writer.append(self.memory_root / "agent" / "journal.jsonl", json.dumps({
                        "time": now, "kind": record.kind, "title": record.title,
                        "content": record.content, "trust": record.trust,
                    }, ensure_ascii=False) + "\n")
                
                self._conn.commit()
                # We cap the hot cache here to prevent memory leak in long sessions.
                del self._hot_cache[:-MAX_HOT_CACHE]

            except Exception:
                self._conn.rollback()
                raise

    def remember_sync(self, record: MemoryRecord) -> None:
        self.remember_many_sync([record])

    def _insert_record(self, **kw: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO documents(
              doc_key, source_id, source_path, kind, title, chunk_index, content,
              content_hash, trust, pinned, valid_until, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_key) DO UPDATE SET
              source_id=excluded.source_id,
              source_path=excluded.source_path,
              kind=excluded.kind,
              title=excluded.title,
              chunk_index=excluded.chunk_index,
              content=excluded.content,
              content_hash=excluded.content_hash,
              trust=excluded.trust,
              pinned=excluded.pinned,
              valid_until=excluded.valid_until,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
            """,
            (
                kw["doc_key"], kw["source_id"], kw.get("source_path"), kw["kind"], kw["title"],
                kw["chunk_index"], kw["content"], sha256_text(kw["content"]), float(kw["trust"]),
                int(bool(kw["pinned"])), kw.get("valid_until"), json.dumps(kw["metadata"], ensure_ascii=False),
                kw["now"], kw["now"],
            ),
        )

    async def search(self, query: str, *, limit: int = MAX_RESULTS, min_trust: float = 0.35, kinds: Sequence[str] | None = None) -> list[dict[str, Any]]:
        return self.search_sync(query, limit=limit, min_trust=min_trust, kinds=kinds)

    def search_sync(self, query: str, *, limit: int = MAX_RESULTS, min_trust: float = 0.35, kinds: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Perform a keyword search using BM25 ranking and result diversification.
        
        Unlike standard SQL 'LIKE' matches, BM25 ranks results by word 
        uniqueness and frequency. This ensures that technical terms in 
        the query yield the most relevant results first.
        """
        self.bootstrap_sync()
        tokens = TOKEN_RE.findall(query.lower())[:10]
        if not tokens:
            return []
            
        fts_query = " OR ".join(f'"{t}"' for t in tokens)
        
        params: list[Any] = [fts_query, min_trust, utc_now()]
        kind_clause = ""
        if kinds:
            kind_clause = " AND d.kind IN (" + ",".join("?" for _ in kinds) + ")"
            params.extend(kinds)
        
        params.append(max(limit * 4, 32))

        with self._lock:
            try:
                rows = self._conn.execute(
                    f"""
                    SELECT d.id, d.doc_key, d.source_id, d.kind, d.title, d.content, d.trust,
                           d.pinned, d.valid_until, d.metadata_json, d.updated_at,
                           bm25(documents_fts) AS rank
                    FROM documents_fts
                    JOIN documents d ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ?
                      AND (d.pinned = 1 OR d.trust >= ?)
                      AND (d.valid_until IS NULL OR d.valid_until > ?)
                      {kind_clause}
                    ORDER BY d.pinned DESC, d.trust DESC, rank ASC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()

                selected = self._diversify(rows, limit)
                if selected:
                    self._conn.executemany(
                        "UPDATE documents SET access_count = access_count + 1 WHERE id = ?", 
                        [(r["id"],) for r in selected]
                    )
                    self._conn.commit()
                return [self._row_to_dict(r) for r in selected]
            except sqlite3.Error as e:
                logger.error(f"Search failed: {e}")
                return []

    def _diversify(self, rows: Sequence[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
        """Ensure the search results spread across multiple distinct sources.
        
        In RAG (Retrieval-Augmented Generation), prompt space is expensive. 
        If we fill 8 results from one file, we lose context from others. 
        This logic ensures a 'spread' across multiple sources for a broader 
        contextual view.
        """
        out: list[sqlite3.Row] = []
        seen_hashes: set[str] = set()
        per_source: dict[str, int] = {}

        for row in rows:
            content_hash = sha256_text(row["content"][:1000])

            if content_hash in seen_hashes:
                continue

            count = per_source.get(row["source_id"], 0)

            if count >= 2 and not row["pinned"]:
                continue

            seen_hashes.add(content_hash)
            per_source[row["source_id"]] = count + 1
            out.append(row)

            if len(out) >= limit:
                break

        return out

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Converts a database row into a clean dictionary for the agent."""
        return {
            "source": row["source_id"],
            "kind": row["kind"],
            "title": row["title"],
            "content": row["content"],
            "trust": float(row["trust"]),
            "pinned": bool(row["pinned"]),
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }

    async def essential_context(self, user_query: str = "") -> str:
        return self.essential_context_sync(user_query)

    def essential_context_sync(self, user_query: str = "") -> str:
        """Assemble the foundational context required for every agent interaction.
        
        This method combines the 'Bedrock' identity (Soul, Rules), the 
        recent 'Hot Cache' of the session, and the most relevant search hits 
        into a single context block.
        
        It is designed to be the single source of truth for the agent's 
        'working memory' before it processes the user's latest message.
        """
        self.bootstrap_sync()
        core_parts = []

        for path in [self.memory_root / "soul.md", self.memory_root / "rules.md"]:
            if path.exists():
                core_parts.append(f"### {path.name}\n{bounded_read_text(path)}")

        hot = [f"- {r.kind}: {r.content[:500]}" for r in self._hot_cache[-MAX_HOT_CACHE:]]
        hits = self.search_sync(user_query, limit=6) if user_query else []
        retrieved = [f"- [{h['kind']}] {h['content']}" for h in hits]
        
        text = "\n\n".join(core_parts)
        if hot: text += "\n\n## Recent Context:\n" + "\n".join(hot)
        if retrieved: text += "\n\n## Relevant Memories:\n" + "\n".join(retrieved)

        return text[:MAX_ESSENTIAL_CHARS]


_default_memory: LocalFirstMemory | None = None
_default_lock = threading.RLock()


def get_memory() -> LocalFirstMemory:
    global _default_memory

    with _default_lock:
        if _default_memory is None:
            _default_memory = LocalFirstMemory()

        return _default_memory
