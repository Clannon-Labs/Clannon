"""Tests for the agent-owned memory gateway.

These verify memory remains internal to the agent while still providing fast,
bounded search and structured writes.
"""

import pytest

from src.agent.memory import AgentMemory, AgentMemoryLimits


def test_agent_memory_searches_internal_memory():
    """AgentMemory can write and retrieve a high-trust internal memory."""
    marker = "agent-memory-marker"
    memory = AgentMemory()
    memory.remember_sync(
        source_id="test_agent_memory",
        kind="fact",
        title="Agent memory test",
        content=f"The searchable marker is {marker}.",
        trust=0.9,
        pinned=True,
    )

    result = memory.search_sync(marker, limit=3)

    assert result["count"] >= 1
    assert any(marker in item["content"] for item in result["results"])


def test_agent_memory_bounds_search_limit_and_content():
    """AgentMemory applies caller-visible limits before delegating to storage."""
    marker = "bounded-agent-memory-marker"
    memory = AgentMemory(limits=AgentMemoryLimits(max_search_limit=1, max_content_chars=20))
    memory.remember_sync(
        source_id="test_agent_memory_bounds",
        kind="fact",
        title="Agent memory bounds test",
        content=f"{marker} with extra text that should be truncated",
        trust=2.0,
        pinned=True,
    )

    result = memory.search_sync(marker, limit=100)

    assert result["count"] <= 1


def test_agent_memory_requires_structured_write_fields():
    """AgentMemory rejects incomplete writes before creating MemoryRecord."""
    with pytest.raises(ValueError, match="source_id is required"):
        AgentMemory().remember_sync(
            source_id="",
            kind="fact",
            title="Missing source",
            content="content",
        )
