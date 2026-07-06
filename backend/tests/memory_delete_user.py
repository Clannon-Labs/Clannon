"""
`MemoryManager.delete_user` — right-to-erasure across ALL tiers, not just
the four Qdrant vector tiers.

Pre-existing gap, found while closing out the Mission Engine graph substrate
(`core/memory/HANDOFF_batch.md`): `delete_user()`'s own docstring promised
"purge every tier for this user" but only ever called `store.delete_user`
(Qdrant) — the graph tier (CodeFile + Mission/Task, `core/memory/
graph_store.py` + `mission_graph_store.py`) was silently skipped entirely.
Same shape as the cross-batch `delete_user` gap already fixed elsewhere.

Hermetic: `store.delete_user` (Qdrant) is monkeypatched to a recorder so this
file needs no live Qdrant instance, matching `memory_store_fault.py`'s
convention. The graph half is proven against a REAL embedded Kuzu db (no
mock needed — Kuzu has no server to be down) via the `_fresh_graph_store`
autouse fixture in `tests/conftest.py`.

  ✓ MemoryManager.delete_user calls store.delete_user (vector tiers) AND
    graph_manager.manager.delete_user (graph tier) — not just one of the two
  ✓ end-to-end: real CodeFile + Mission/Task graph data written for a user
    is actually gone after MemoryManager.delete_user, another tenant's
    identically-shaped data is untouched

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_delete_user.py -v
"""
from __future__ import annotations

import asyncio

import core.memory.graph_store as graph_store
import core.memory.store as _store
from core.memory.graph_manager import manager as graph_manager
from core.memory.manager import MemoryManager
from foundation import GraphNode, GraphScope, NodeLabel


def test_delete_user_purges_both_the_vector_tiers_and_the_graph_tier(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(_store, "delete_user", lambda user_id: calls.append(("vector", user_id)))

    async def go():
        await MemoryManager().delete_user("u1")
    asyncio.run(go())

    assert ("vector", "u1") in calls, "the Qdrant vector tiers must still be purged"


def test_delete_user_end_to_end_clears_real_codefile_and_mission_task_graph_data():
    async def go():
        owner, other = GraphScope(user_id="owner"), GraphScope(user_id="other")
        code_node = GraphNode(
            node_id=graph_store.node_id(owner, "a.py"), label=NodeLabel.CODE_FILE, scope=owner,
            properties={"path": "a.py"},
        )
        other_code_node = GraphNode(
            node_id=graph_store.node_id(other, "a.py"), label=NodeLabel.CODE_FILE, scope=other,
            properties={"path": "a.py"},
        )
        task_node = GraphNode(
            node_id=graph_store.node_id(owner, "t1"), label=NodeLabel.TASK, scope=owner,
            properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        await graph_manager.write(owner, [code_node, task_node], [])
        await graph_manager.write(other, [other_code_node], [])

        await MemoryManager().delete_user("owner")

        assert (await graph_manager.lookup(owner, natural_key="a.py")).nodes == []
        assert (await graph_manager.members(owner, NodeLabel.TASK, parent_id="m1")).nodes == []
        # another tenant's identically-shaped graph data must survive
        assert (await graph_manager.lookup(other, natural_key="a.py")).nodes != []
    asyncio.run(go())
