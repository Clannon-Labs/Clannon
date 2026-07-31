"""
`core/memory`'s consumer side of the config-depth externalization
(`config/backend/memory.yaml` + the two `budget.yaml` fields, `settings.
MemoryConfig` — placed by the backend-agent, `015b46f`). `tests/config_
memory.py` covers the loader/validation seam; this covers that `core/memory`
actually READS from it rather than a coincidentally-matching hardcoded
literal.

Ratified 2026-07-06 (`proposals/archive/to-backend/2026-07-06_memory-
config-depth-proposal.md`): every constant below equals its prior hardcoded
value (behavior-preserving) — this file pins that equality AND, for the one
call-time (not import-time-frozen) read, proves actual causation rather than
coincidence.

Manager-split note (2026-07-06): the constants this file pins now live in
`hydration.py` (read side) / `write_policy.py` (write side) / `tiers.py`
(shared TIER_TRUST/TIER_FLOOR), not `manager.py` — `manager.py` is now a
thin `MemoryPort` door delegating to both. `_MAX_CONTENT_CHARS` exists as
an independent module-level read in BOTH hydration.py and write_policy.py
(each reads `settings.MEMORY.max_content_chars` directly — a bare scalar
read, not logic worth sharing, same reasoning as `graph_extract.py`/
`graph_store.py`'s independent `MAX_HOPS_CEILING` reads) — this file pins
both copies.

  ✓ hydration.py's read-side constants and write_policy.py's write-side
    constants equal settings.MEMORY / settings.BUDGET, not a re-hardcoded
    literal
  ✓ tiers.TIER_TRUST/TIER_FLOOR equal settings.MEMORY.tier_trust/tier_floor,
    with TIER_TRUST's int-cast preserved (flows into MemoryItem.trust, an
    `int` field, and the Qdrant payload)
  ✓ embeddings.py's retry backoff equals settings.MEMORY.embed_retry_after_s
  ✓ graph_store.MAX_HOPS_CEILING equals settings.MEMORY.graph_max_hops_ceiling
  ✓ graph_extract.CodeImportGraph.breaks_if_removed's hop-ceiling default
    equals the SAME config value graph_store.MAX_HOPS_CEILING reads (the
    §Phase-3.5-flagged duplicate-literal fix) — proven without a circular
    import (graph_extract can't import graph_store) by reading settings
    directly
  ✓ store.py's Qdrant client timeout is GENUINELY wired (not just
    coincidentally equal): a fake QdrantClient captures the timeout kwarg
    it's constructed with — the one constant here read at call-time rather
    than frozen at import, so it's provable without a module reload

D1 slice (2026-07-06, f628a0b): the MEMORY_* group formerly in
`foundation/vocab/constants.py` — same equality-pin / causation-proof split:
  ✓ hydration.py's _SEARCH_K/_RELEVANCE_FLOOR and store.search's default
    `limit` equal settings.MEMORY (import-frozen, equality-pin)
  ✓ hydration._embed_bounded's read deadline plus curator/writer retry counts
    are GENUINELY wired (call-time reads,
    same causation-proof shape as the Qdrant timeout above)

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_config_wiring.py -v
"""
from __future__ import annotations

import inspect

import settings
import core.memory.curator as curator
import core.memory.embeddings as embeddings
import core.memory.graph_extract as graph_extract
import core.memory.graph_store as graph_store
import core.memory.hydration as hydration
import core.memory.store as store
import core.memory.tiers as tiers
import core.memory.write_policy as write_policy
import core.memory.writer as writer
from foundation import MemoryStore, MemoryTurn


def test_tier_trust_and_floor_match_settings():
    assert tiers.TIER_TRUST == {
        MemoryStore.WIKI: settings.MEMORY.tier_trust.wiki,
        MemoryStore.SEMANTIC: settings.MEMORY.tier_trust.semantic,
        MemoryStore.EPISODIC: settings.MEMORY.tier_trust.episodic,
        MemoryStore.PROCEDURAL: settings.MEMORY.tier_trust.procedural,
    }
    # TierTrust's fields are `float` in settings.py, but TIER_TRUST's values
    # flow into MemoryItem.trust (an `int` field) and the Qdrant payload —
    # must stay a genuine int, not a silently-introduced 3.0.
    assert all(isinstance(v, int) for v in tiers.TIER_TRUST.values())
    assert tiers.TIER_FLOOR == {
        MemoryStore.WIKI: settings.MEMORY.tier_floor.wiki,
        MemoryStore.SEMANTIC: settings.MEMORY.tier_floor.semantic,
        MemoryStore.EPISODIC: settings.MEMORY.tier_floor.episodic,
        MemoryStore.PROCEDURAL: settings.MEMORY.tier_floor.procedural,
    }


def test_hydration_constants_match_settings_not_a_rehardcoded_literal():
    assert hydration._RECENCY_HALF_LIFE_S == settings.MEMORY.recency_half_life_s
    assert hydration._RECENCY_FLOOR == settings.MEMORY.recency_floor
    assert hydration._MAX_CONTENT_CHARS == settings.MEMORY.max_content_chars
    assert hydration._SEARCH_K == settings.MEMORY.search_top_k
    assert hydration._RELEVANCE_FLOOR == settings.MEMORY.relevance_floor
    assert hydration._DEFAULT_BUDGET_TOKENS == settings.BUDGET.default_memory_budget_tokens
    assert hydration._CHARS_PER_TOKEN == settings.BUDGET.memory_chars_per_token


def test_write_policy_constants_match_settings_not_a_rehardcoded_literal():
    assert write_policy._MIN_ACCEPT_CONFIDENCE == settings.MEMORY.min_accept_confidence
    assert write_policy._DEDUP_SIMILARITY == settings.MEMORY.dedup_similarity
    assert write_policy._MAX_CONTENT_CHARS == settings.MEMORY.max_content_chars
    assert write_policy._SUPERSESSION_FLOOR == settings.MEMORY.supersession_floor
    assert write_policy._SUPERSESSION_TIMEOUT_S == settings.MEMORY.supersession_timeout_s


def test_embeddings_retry_backoff_matches_settings():
    assert embeddings._RETRY_AFTER_S == settings.MEMORY.embed_retry_after_s


def test_graph_store_hop_ceiling_matches_settings():
    assert graph_store.MAX_HOPS_CEILING == settings.MEMORY.graph_max_hops_ceiling


def test_graph_extract_default_matches_graph_store_no_second_literal():
    """The §Phase-3.5-flagged drift fix: graph_extract's own default must
    equal graph_store's, both sourced from the SAME config value — not two
    independently hardcoded 20s that happen to match today."""
    default = inspect.signature(graph_extract.CodeImportGraph.breaks_if_removed).parameters["max_hops"].default
    assert default == graph_store.MAX_HOPS_CEILING == settings.MEMORY.graph_max_hops_ceiling


def test_store_qdrant_timeout_is_genuinely_wired_not_coincidental(monkeypatch):
    """Proves causation, not just equality: a fake QdrantClient captures the
    timeout it's actually constructed with, using a DIFFERENT value than
    today's default so a hardcoded-literal regression would fail this even
    if it happened to equal 5 by coincidence. `settings.MEMORY` is a frozen
    pydantic model (can't patch one field in place), so the whole singleton
    is swapped for a copy with one field overridden — the real causal path
    (`store._qdrant()` reads `settings.MEMORY.qdrant_request_timeout_s` at
    CALL time, not at import time, so this is a live read, not a frozen
    module-level constant)."""
    captured = {}

    class _FakeQdrantClient:
        def __init__(self, url, timeout):
            captured["timeout"] = timeout

    monkeypatch.setattr("qdrant_client.QdrantClient", _FakeQdrantClient)
    monkeypatch.setattr(store, "_client", None)
    monkeypatch.setattr(store, "_down_until", 0.0)

    sentinel = 12.5   # distinct from the real default (5) — rules out coincidence
    patched_memory = settings.MemoryConfig(**{**settings.MEMORY.model_dump(), "qdrant_request_timeout_s": sentinel})
    monkeypatch.setattr(settings, "MEMORY", patched_memory)

    client = store._qdrant()
    assert client is not None
    assert captured.get("timeout") == sentinel


def test_store_search_default_limit_matches_settings():
    default = inspect.signature(store.search).parameters["limit"].default
    assert default == settings.MEMORY.search_top_k


def test_embed_bounded_read_timeout_is_genuinely_wired(monkeypatch):
    """Causation, not coincidence: a hanging embed only trips the (patched,
    near-zero) deadline if _embed_bounded is actually reading
    settings.MEMORY.read_timeout_s live, not a frozen default."""
    import asyncio as _asyncio

    async def _hanging_embed(texts):
        await _asyncio.sleep(5)
        return [[0.0] for _ in texts]

    monkeypatch.setattr(embeddings, "embed", _hanging_embed)
    patched = settings.MemoryConfig(**{**settings.MEMORY.model_dump(), "read_timeout_s": 0.05})
    monkeypatch.setattr(settings, "MEMORY", patched)

    result = _asyncio.run(hydration._embed_bounded("x"))
    assert result is None, "a stalled embed must degrade via the (patched, tiny) read timeout"


def test_memory_agent_retries_are_genuinely_wired(monkeypatch):
    """Curator and one-shot writer judgments both read configured retries."""
    captured = []

    def _fake_build(*args, **kwargs):
        captured.append(kwargs.get("retries"))
        return None

    monkeypatch.setattr(curator, "build_tool_agent", _fake_build)
    monkeypatch.setattr(writer, "build_agent", _fake_build)
    sentinel = 7   # distinct from the real default (2) — rules out coincidence
    patched = settings.MemoryConfig(**{**settings.MEMORY.model_dump(), "distill_max_retries": sentinel})
    monkeypatch.setattr(settings, "MEMORY", patched)

    import asyncio as _asyncio
    turn = MemoryTurn(
        user_id="u", session_id="s", trace_id="t",
        request="task", response="answer",
    )
    assert _asyncio.run(curator.process_turn(turn)) == []
    assert _asyncio.run(writer.judge_supersession("a", "b")) is False

    assert captured == [sentinel, sentinel]
