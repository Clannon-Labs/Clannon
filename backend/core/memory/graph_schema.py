"""
core/memory/graph_schema.py

Every `CREATE NODE/REL TABLE` statement for the shared embedded Kuzu db, in
one place — split out of `graph_store.py` (LAW 2: the DDL blob pushed that
file past the 500-line ceiling once the knowledge-web tables landed).
Schema creation stays centralized here rather than distributed to each
domain's own store module (`mission_graph_store.py`, `knowledge_store.py`)
because those modules already import `graph_store.py` for the shared
connection — this module has no reverse dependency on either, so
`graph_store.py` can import it without a cycle.

`ensure_schema(conn)` is idempotent (each statement no-ops if the table
already exists) and is the ONLY place table DDL is issued; `graph_store.py`
calls it once per fresh connection. Domain modules never issue their own
CREATE TABLE — they only read/write through the tables declared here.
"""
from __future__ import annotations

from typing import Any


def _already_exists(exc: Exception) -> bool:
    return "already exists" in str(exc).lower()


def _create_if_absent(conn: Any, ddl: str) -> None:
    """One CREATE TABLE statement, idempotent — shared so each table isn't
    its own copy-pasted try/except."""
    try:
        conn.execute(ddl)
    except RuntimeError as exc:
        if not _already_exists(exc):
            raise


def ensure_schema(conn: Any) -> None:
    """Create every table this package's stores need, if not already present.
    Order matters: a REL TABLE's FROM/TO tables must exist before it does."""
    # CB2 first slice — code-only import graph.
    _create_if_absent(
        conn,
        "CREATE NODE TABLE CodeFile("
        "id STRING, user_id STRING, repo_id STRING, path STRING, "
        "PRIMARY KEY(id))",
    )
    _create_if_absent(conn, "CREATE REL TABLE IMPORTS(FROM CodeFile TO CodeFile, origin STRING)")

    # Mission Engine (batch phase) — MISSION/TASK nodes, typed task-dependency
    # edges. mission_id lives as a plain property (a filter under user_id, not
    # a GraphScope dimension — ratified 2026-07-05); success_criteria is a
    # native Kuzu STRING[] (Criterion is just {description: str} today, a list
    # of strings is the whole shape, no need for a richer encoding).
    _create_if_absent(
        conn,
        "CREATE NODE TABLE Mission("
        "id STRING, user_id STRING, repo_id STRING, mission_id STRING, "
        "intent STRING, success_criteria STRING[], status STRING, updated_at DOUBLE, "
        "PRIMARY KEY(id))",
    )
    _create_if_absent(
        conn,
        "CREATE NODE TABLE Task("
        "id STRING, user_id STRING, repo_id STRING, task_id STRING, mission_id STRING, "
        "summary STRING, status STRING, evidence STRING, updated_at DOUBLE, "
        "PRIMARY KEY(id))",
    )
    for rel in ("Blocks", "Feeds", "Supersedes"):
        _create_if_absent(conn, f"CREATE REL TABLE {rel}(FROM Task TO Task, origin STRING)")

    # Knowledge web (CB2/CB3/EB3 substrate, ratified 2026-07-06) — Entity is the
    # convergence point (canonical_name is the node identity — see
    # knowledge_store.py); Fact/Claim are CB1's typed-knowledge kind (fact vs
    # assumption) mirrored as separate graph tables, keyed by their originating
    # memory point's vector_id (the fusion pointer IS the identity key here);
    # MediaSegment is CB3's landing node, keyed by a composite segment_key.
    _create_if_absent(
        conn,
        "CREATE NODE TABLE Entity("
        "id STRING, user_id STRING, repo_id STRING, entity_type STRING, "
        "canonical_name STRING, vector_id STRING, updated_at DOUBLE, "
        "PRIMARY KEY(id))",
    )
    for kind in ("Fact", "Claim"):
        _create_if_absent(
            conn,
            f"CREATE NODE TABLE {kind}("
            "id STRING, user_id STRING, repo_id STRING, content STRING, "
            "confidence DOUBLE, vector_id STRING, updated_at DOUBLE, "
            "PRIMARY KEY(id))",
        )
    _create_if_absent(
        conn,
        "CREATE NODE TABLE MediaSegment("
        "id STRING, user_id STRING, repo_id STRING, modality STRING, "
        "source_media_id STRING, start_ts DOUBLE, end_ts DOUBLE, text STRING, "
        "vector_id STRING, updated_at DOUBLE, PRIMARY KEY(id))",
    )
    # RelatesTo/DerivedFrom/AuthoredBy are HETEROGENEOUS-endpoint rels (verified
    # against real Kuzu 0.11.3: multi-pair FROM/TO in one CREATE REL TABLE is
    # supported) — knowledge_store.py's typed-edge registry marks these with a
    # `None` node_table so typed_graph.py matches by id/scope without a label
    # constraint. Contradicts is homogeneous (Claim-to-Claim only).
    _create_if_absent(
        conn,
        "CREATE REL TABLE RelatesTo("
        "FROM Entity TO Entity, FROM Entity TO Fact, FROM Entity TO Claim, "
        "FROM Entity TO MediaSegment, origin STRING)",
    )
    _create_if_absent(conn, "CREATE REL TABLE Contradicts(FROM Claim TO Claim, origin STRING)")
    _create_if_absent(
        conn,
        "CREATE REL TABLE DerivedFrom("
        "FROM Entity TO Task, FROM Fact TO Task, FROM Claim TO Task, "
        "FROM MediaSegment TO Task, origin STRING)",
    )
    _create_if_absent(
        conn, "CREATE REL TABLE AuthoredBy(FROM Fact TO Entity, FROM Claim TO Entity, origin STRING)"
    )
