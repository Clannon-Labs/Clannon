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

  ✓ manager.py's eleven ranking/acceptance/budget constants equal
    settings.MEMORY / settings.BUDGET, not a re-hardcoded literal
  ✓ embeddings.py's retry backoff equals settings.MEMORY.embed_retry_after_s
  ✓ graph_store.MAX_HOPS_CEILING equals settings.MEMORY.graph_max_hops_ceiling
  ✓ graph_extract.CodeImportGraph.breaks_if_removed's hop-ceiling default
    equals the SAME config value graph_store.MAX_HOPS_CEILING reads (the
    §Phase-3.5-flagged duplicate-literal fix) — proven without a circular
    import (graph_extract can't import graph_store) by reading settings
    directly
  ✓ store.py's Qdrant client timeout is GENUINELY wired (not just
    coincidentally equal): a fake QdrantClient captures the timeout kwarg
    it's constructed with, proving a changed config value would change what
    the real client receives — the one constant here that's read at
    call-time rather than frozen at import, so it's provable without a
    module reload

D1 slice (2026-07-06, f628a0b): the MEMORY_* group formerly in
`foundation/vocab/constants.py` — same equality-pin / causation-proof split:
  ✓ manager.py's _SEARCH_K/_RELEVANCE_FLOOR and store.search's default
    `limit` equal settings.MEMORY (import-frozen, equality-pin)
  ✓ manager._embed_bounded's read deadline and writer.distill/
    judge_supersession's retry count are GENUINELY wired (call-time reads,
    same causation-proof shape as the Qdrant timeout above)

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_config_wiring.py -v
"""
from __future__ import annotations

import settings
import core.memory.embeddings as embeddings
import core.memory.graph_extract as graph_extract
import core.memory.graph_store as graph_store
import core.memory.store as store
# core/memory/__init__.py does `from .manager import MemoryManager, manager`,
# which reassigns the PACKAGE attribute `core.memory.manager` to the
# singleton instance — `import core.memory.manager as manager` would then
# bind to that instance, not the submodule. A direct `from` import of the
# submodule's names (the same convention tests/memory_supersession.py etc.
# already use) sidesteps this entirely.
from core.memory.manager import (
    _CHARS_PER_TOKEN,
    _DEDUP_SIMILARITY,
    _DEFAULT_BUDGET_TOKENS,
    _MAX_CONTENT_CHARS,
    _MIN_ACCEPT_CONFIDENCE,
    _RECENCY_FLOOR,
    _RECENCY_HALF_LIFE_S,
    _RELEVANCE_FLOOR,
    _SEARCH_K,
    _SUPERSESSION_FLOOR,
    _SUPERSESSION_TIMEOUT_S,
    _TIER_FLOOR,
    _TIER_TRUST,
    _embed_bounded,
)
import core.memory.writer as writer
from foundation import MemoryStore


def test_manager_constants_match_settings_not_a_rehardcoded_literal():
    assert _TIER_TRUST == {
        MemoryStore.WIKI: settings.MEMORY.tier_trust.wiki,
        MemoryStore.SEMANTIC: settings.MEMORY.tier_trust.semantic,
        MemoryStore.EPISODIC: settings.MEMORY.tier_trust.episodic,
        MemoryStore.PROCEDURAL: settings.MEMORY.tier_trust.procedural,
    }
    # TierTrust's fields are `float` in settings.py, but _TIER_TRUST's values
    # flow into MemoryItem.trust (an `int` field) and the Qdrant payload —
    # must stay a genuine int, not a silently-introduced 3.0.
    assert all(isinstance(v, int) for v in _TIER_TRUST.values())
    assert _TIER_FLOOR == {
        MemoryStore.WIKI: settings.MEMORY.tier_floor.wiki,
        MemoryStore.SEMANTIC: settings.MEMORY.tier_floor.semantic,
        MemoryStore.EPISODIC: settings.MEMORY.tier_floor.episodic,
        MemoryStore.PROCEDURAL: settings.MEMORY.tier_floor.procedural,
    }
    assert _RECENCY_HALF_LIFE_S == settings.MEMORY.recency_half_life_s
    assert _RECENCY_FLOOR == settings.MEMORY.recency_floor
    assert _MIN_ACCEPT_CONFIDENCE == settings.MEMORY.min_accept_confidence
    assert _DEDUP_SIMILARITY == settings.MEMORY.dedup_similarity
    assert _MAX_CONTENT_CHARS == settings.MEMORY.max_content_chars
    assert _SUPERSESSION_FLOOR == settings.MEMORY.supersession_floor
    assert _SUPERSESSION_TIMEOUT_S == settings.MEMORY.supersession_timeout_s
    assert _DEFAULT_BUDGET_TOKENS == settings.BUDGET.default_memory_budget_tokens
    assert _CHARS_PER_TOKEN == settings.BUDGET.memory_chars_per_token


def test_embeddings_retry_backoff_matches_settings():
    assert embeddings._RETRY_AFTER_S == settings.MEMORY.embed_retry_after_s


def test_graph_store_hop_ceiling_matches_settings():
    assert graph_store.MAX_HOPS_CEILING == settings.MEMORY.graph_max_hops_ceiling


def test_graph_extract_default_matches_graph_store_no_second_literal():
    """The §Phase-3.5-flagged drift fix: graph_extract's own default must
    equal graph_store's, both sourced from the SAME config value — not two
    independently hardcoded 20s that happen to match today."""
    import inspect
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


# ─────────────────────────────────────────────────────────────────────────────
# D1 slice (f628a0b) — the former foundation.constants.MEMORY_* group
# ─────────────────────────────────────────────────────────────────────────────

def test_search_k_and_relevance_floor_match_settings():
    assert _SEARCH_K == settings.MEMORY.search_top_k
    assert _RELEVANCE_FLOOR == settings.MEMORY.relevance_floor


def test_store_search_default_limit_matches_settings():
    import inspect
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

    result = _asyncio.run(_embed_bounded("x"))
    assert result is None, "a stalled embed must degrade via the (patched, tiny) read timeout"


def test_writer_retries_are_genuinely_wired(monkeypatch):
    """Causation proof for both writer.py call sites: a fake build_agent
    captures the `retries` kwarg it's actually invoked with. Returns None
    (a bogus handle) rather than raising — build_agent() is called OUTSIDE
    both functions' try/except, so a raise here would propagate uncaught;
    the None handle instead makes the (real) run_structured() fail, which
    IS inside the try/except, so distill()/judge_supersession() degrade
    normally (best-effort, never raises)."""
    captured = []

    def _fake_build_agent(*args, **kwargs):
        captured.append(kwargs.get("retries"))
        return None

    monkeypatch.setattr(writer, "build_agent", _fake_build_agent)
    sentinel = 7   # distinct from the real default (2) — rules out coincidence
    patched = settings.MemoryConfig(**{**settings.MEMORY.model_dump(), "distill_max_retries": sentinel})
    monkeypatch.setattr(settings, "MEMORY", patched)

    import asyncio as _asyncio
    assert _asyncio.run(writer.distill("task", "answer", [])) == []
    assert _asyncio.run(writer.judge_supersession("a", "b")) is False

    assert captured == [sentinel, sentinel]
