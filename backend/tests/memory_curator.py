"""Memory Manager-owned curator tools, provenance, listing, and deletion."""

import asyncio
from types import SimpleNamespace

from foundation import (
    MemoryItem,
    MemoryKind,
    MemorySaver,
    MemoryStore,
    MemoryTurn,
    MemoryWriteProposal,
)
from core.memory import curator
from core.memory.manager import MemoryManager
import core.memory.store as store_mod
import core.memory.write_policy as write_policy


def _turn(**overrides):
    values = {
        "user_id": "user-1",
        "session_id": "session-1",
        "trace_id": "trace-1",
        "request": "Help plan the Meridian launch.",
        "response": "Launch approved for September.",
        "findings": ("Meridian is a skincare brand.",),
        "decisions": ("Approved September launch.",),
        "participants": ("Priya", "Sam"),
    }
    values.update(overrides)
    return MemoryTurn(**values)


def _fake_agent(monkeypatch, drive):
    captured = {}

    def fake_build(*args, **kwargs):
        captured["tools"] = {tool.__name__: tool for tool in kwargs["tools"]}
        captured["build"] = kwargs
        return object()

    async def fake_run(*args, **kwargs):
        captured["run"] = kwargs
        return await drive(captured["tools"])

    monkeypatch.setattr(curator, "build_tool_agent", fake_build)
    monkeypatch.setattr(curator, "run_structured", fake_run)
    return captured


def test_low_signal_turn_can_complete_with_zero_writes(monkeypatch):
    async def drive(_tools):
        return curator.CuratorVerdict(complete=True, rationale="nothing durable")

    _fake_agent(monkeypatch, drive)
    called = {"persist": 0}

    async def persist(*args):
        called["persist"] += 1
        return []

    monkeypatch.setattr(curator.write_policy, "persist_curated", persist)
    assert asyncio.run(MemoryManager().process_turn(_turn())) == []
    assert called["persist"] == 0


def test_curator_can_stage_all_three_inferred_tiers_with_trusted_provenance(monkeypatch):
    async def drive(tools):
        assert "staged" in await tools["save_memory"](
            "semantic",
            "Meridian is a skincare brand.",
            "Useful client identity.",
            0.95,
            "fact",
            "turn finding",
        )
        assert "staged" in await tools["save_memory"](
            "episodic",
            "Meridian's September launch was approved.",
            "Meaningful project milestone.",
            0.9,
            "decision",
            "decision log",
        )
        assert "staged" in await tools["save_memory"](
            "procedural",
            "User prefers launch plans reviewed by Priya before execution.",
            "Stable approval workflow.",
            0.85,
            "assumption",
        )
        return curator.CuratorVerdict(complete=True)

    captured = _fake_agent(monkeypatch, drive)

    async def persist(turn, proposals):
        captured["turn"] = turn
        captured["proposals"] = proposals
        return [
            MemoryItem(
                store=proposal.store,
                content=proposal.content,
                memory_id=f"id-{index}",
                trace_id=turn.trace_id,
                saved_by=MemorySaver.MEMORY_CURATOR,
            )
            for index, proposal in enumerate(proposals)
        ]

    monkeypatch.setattr(curator.write_policy, "persist_curated", persist)
    result = asyncio.run(MemoryManager().process_turn(_turn()))

    assert {proposal.store for proposal in captured["proposals"]} == {
        MemoryStore.SEMANTIC,
        MemoryStore.EPISODIC,
        MemoryStore.PROCEDURAL,
    }
    assert all(proposal.rationale for proposal in captured["proposals"])
    assert all(proposal.participants == "Priya,Sam" for proposal in captured["proposals"])
    assert all(item.trace_id == "trace-1" for item in result)
    assert all(item.saved_by is MemorySaver.MEMORY_CURATOR for item in result)


def test_save_tool_rejects_forbidden_tiers_missing_policy_and_transcripts(monkeypatch):
    rejected = []

    async def drive(tools):
        save = tools["save_memory"]
        rejected.append(await save("wiki", "x", "why", 0.9, "fact", "source"))
        rejected.append(await save("working", "x", "why", 0.9, "assumption"))
        rejected.append(await save("semantic", "x", "", 0.9, "assumption"))
        rejected.append(await save("semantic", "x", "why", 0.1, "assumption"))
        rejected.append(
            await save(
                "semantic",
                "x" * (curator.settings.MEMORY.max_content_chars + 1),
                "why",
                0.9,
                "assumption",
            )
        )
        rejected.append(
            await save(
                "episodic",
                "task: Help plan the Meridian launch. | answer: Launch approved for September.",
                "turn transcript",
                0.9,
                "assumption",
            )
        )
        return curator.CuratorVerdict(complete=True)

    _fake_agent(monkeypatch, drive)
    called = {"persist": 0}

    async def persist(*args):
        called["persist"] += 1
        return []

    monkeypatch.setattr(curator.write_policy, "persist_curated", persist)
    assert asyncio.run(MemoryManager().process_turn(_turn())) == []
    assert len(rejected) == 6
    assert all(message.startswith("rejected:") for message in rejected)
    assert called["persist"] == 0


def test_curator_fault_discards_actions_before_any_write(monkeypatch):
    async def drive(tools):
        await tools["save_memory"](
            "semantic",
            "Meridian is a skincare brand.",
            "Useful later.",
            0.9,
            "fact",
            "turn finding",
        )
        raise RuntimeError("provider failed after tool call")

    _fake_agent(monkeypatch, drive)
    called = {"persist": 0}

    async def persist(*args):
        called["persist"] += 1
        return []

    monkeypatch.setattr(curator.write_policy, "persist_curated", persist)
    assert asyncio.run(MemoryManager().process_turn(_turn())) == []
    assert called["persist"] == 0


def test_curated_persistence_sets_trace_and_saver_in_store_payload(monkeypatch):
    captured = {}

    async def fake_embed(_texts):
        return [[0.1, 0.2]]

    async def no_graph_twin(*args):
        return None

    def fake_upsert(tier, **kwargs):
        captured["tier"] = tier
        captured.update(kwargs)
        return "memory-1"

    monkeypatch.setattr(write_policy.embeddings, "embed", fake_embed)
    monkeypatch.setattr(write_policy.store, "search", lambda *args: [])
    monkeypatch.setattr(write_policy.store, "upsert", fake_upsert)
    monkeypatch.setattr(write_policy, "_write_graph_twin", no_graph_twin)
    proposal = MemoryWriteProposal(
        store=MemoryStore.SEMANTIC,
        content="Meridian is a skincare brand.",
        rationale="Useful client identity.",
        confidence=0.95,
        kind=MemoryKind.FACT,
        source="turn finding",
        participants="Priya,Sam",
    )

    result = asyncio.run(write_policy.persist_curated(_turn(), [proposal]))

    assert captured["trace_id"] == "trace-1"
    assert captured["saved_by"] == "memory_curator"
    assert captured["participants"] == "Priya,Sam"
    assert result[0].memory_id == "memory-1"
    assert result[0].saved_by is MemorySaver.MEMORY_CURATOR


def test_search_tool_uses_captured_user_scope_and_hard_result_cap(monkeypatch):
    async def fake_embed(_texts):
        return [[0.1, 0.2]]

    scopes = []

    def fake_search(tier, user_id, vector, limit):
        scopes.append((tier, user_id, limit))
        return [
            {
                "id": f"{tier.value}-{index}",
                "content": f"memory {index}",
                "score": 1.0 - index / 100,
            }
            for index in range(20)
        ]

    monkeypatch.setattr(curator.embeddings, "embed", fake_embed)
    monkeypatch.setattr(curator.store, "search", fake_search)
    observed = {}

    async def drive(tools):
        observed["hits"] = await tools["search_memory"]("Meridian", 99)
        return curator.CuratorVerdict(complete=True)

    _fake_agent(monkeypatch, drive)
    asyncio.run(MemoryManager().process_turn(_turn()))

    assert len(observed["hits"]) == 10
    assert scopes and all(user_id == "user-1" for _tier, user_id, _limit in scopes)
    assert all(limit == 10 for _tier, _user_id, limit in scopes)


def test_list_entries_covers_every_inferred_tier_and_surfaces_provenance(monkeypatch):
    seen = []

    def fake_list(tier, user_id, limit):
        seen.append((tier, user_id, limit))
        return [{
            "id": f"{tier.value}-id",
            "content": f"{tier.value} content",
            "created_at": 10.0,
            "session_id": "session-1",
            "trace_id": "trace-1",
            "saved_by": "memory_curator",
            "source": "turn evidence",
            "participants": "Priya,Sam",
            "confidence": 0.9,
            "rationale": "useful later",
            "kind": "assumption",
        }]

    monkeypatch.setattr(store_mod, "list_entries", fake_list)
    result = asyncio.run(MemoryManager().list_entries("user-1"))

    assert {item.store for item in result} == {
        MemoryStore.SEMANTIC,
        MemoryStore.EPISODIC,
        MemoryStore.PROCEDURAL,
    }
    assert all(item.memory_id.endswith("-id") for item in result)
    assert all(item.saved_by is MemorySaver.MEMORY_CURATOR for item in result)
    assert all(item.trace_id == "trace-1" and item.participants == "Priya,Sam" for item in result)
    assert seen and all(user_id == "user-1" for _tier, user_id, _limit in seen)


def test_manager_delete_is_fail_closed_and_non_disclosing(monkeypatch):
    calls = []

    def fake_delete(user_id, memory_id):
        calls.append((user_id, memory_id))
        return memory_id == "owned"

    monkeypatch.setattr(store_mod, "delete_entry", fake_delete)
    manager = MemoryManager()

    assert asyncio.run(manager.delete_entry("", "owned")) is False
    assert asyncio.run(manager.delete_entry("user-1", "")) is False
    assert asyncio.run(manager.delete_entry("user-1", "foreign")) is False
    assert asyncio.run(manager.delete_entry("user-1", "unknown")) is False
    assert asyncio.run(manager.delete_entry("user-1", "owned")) is True
    assert calls == [
        ("user-1", "foreign"),
        ("user-1", "unknown"),
        ("user-1", "owned"),
    ]


def test_store_list_and_delete_recheck_tenant_ownership(monkeypatch):
    class FakeClient:
        deleted = []

        def collection_exists(self, _collection):
            return True

        def scroll(self, _collection, **kwargs):
            assert kwargs["scroll_filter"] == "scope:user-1"
            return (
                [
                    SimpleNamespace(id="owned", payload={"user_id": "user-1", "content": "ok"}),
                    SimpleNamespace(id="leak", payload={"user_id": "user-2", "content": "secret"}),
                ],
                None,
            )

        def retrieve(self, collection, ids, **_kwargs):
            owner = (
                "user-1"
                if ids[0] == "owned-procedural"
                and collection == store_mod.COLLECTIONS[MemoryStore.PROCEDURAL]
                else "user-2"
            )
            return [SimpleNamespace(id=ids[0], payload={"user_id": owner})]

        def delete(self, collection, points_selector):
            self.deleted.append((collection, points_selector.points))

    client = FakeClient()
    monkeypatch.setattr(store_mod, "_qdrant", lambda: client)
    monkeypatch.setattr(store_mod, "_user_filter", lambda user_id: f"scope:{user_id}")

    listed = store_mod.list_entries(MemoryStore.SEMANTIC, "user-1", 10)
    assert [item["id"] for item in listed] == ["owned"]
    assert store_mod.delete_entry("user-1", "foreign") is False
    assert store_mod.delete_entry("user-1", "owned-procedural") is True
    assert client.deleted == [
        (
            store_mod.COLLECTIONS[MemoryStore.PROCEDURAL],
            ["owned-procedural"],
        )
    ]
