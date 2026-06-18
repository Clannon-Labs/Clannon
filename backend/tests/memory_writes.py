"""
Memory write hygiene: the `remember` tool (the orchestrator's path to long-term
memory — fixes "can't save when asked" + empty semantic/procedural) and the
substantive-turn gate (so trivial exchanges don't flood episodic).
"""

import asyncio
from types import SimpleNamespace

from foundation import MemoryStore
from registry.capabilities.handler.support import build_orchestrator_tools
from core.orchestrator.orchestrator import _is_substantive_turn


def _remember_tool():
    return next(t for t in build_orchestrator_tools([], []) if getattr(t, "__name__", "") == "remember")


def test_remember_tool_is_always_available():
    assert _remember_tool() is not None


def test_remember_proposes_high_confidence_semantic_and_procedural_writes():
    remember = _remember_tool()
    writes: list = []
    ctx = SimpleNamespace(deps=SimpleNamespace(ctx=SimpleNamespace(memory_writes_requested=writes)))

    msg = asyncio.run(remember(ctx, "The user's main client is Acme Corp.", "fact"))
    asyncio.run(remember(ctx, "The user wants reports under one page.", "preference"))

    assert len(writes) == 2
    assert writes[0].store == MemoryStore.SEMANTIC      # fact -> semantic
    assert writes[1].store == MemoryStore.PROCEDURAL    # preference -> procedural
    # high confidence clears the manager's write-policy floor (so it actually persists)
    assert all(w.confidence >= 0.9 for w in writes)
    assert "saved" in msg.lower()

    # empty content is a no-op, not a write
    asyncio.run(remember(ctx, "   ", "fact"))
    assert len(writes) == 2


def test_substantive_gate_skips_trivial_keeps_real_turns():
    none = SimpleNamespace(expert_findings=[], tool_calls=[])
    # a bare greeting -> NOT substantive (won't be dumped to episodic)
    assert not _is_substantive_turn(SimpleNamespace(content="hey"), SimpleNamespace(text="hello"), none)
    # a real question (long enough task) -> substantive
    assert _is_substantive_turn(
        SimpleNamespace(content="explain how photosynthesis works, in detail please"),
        SimpleNamespace(text="x"), none,
    )
    # a real answer (long) -> substantive even on a short prompt
    assert _is_substantive_turn(SimpleNamespace(content="why?"), SimpleNamespace(text="y" * 250), none)
    # any turn that did real work (experts/tools) -> substantive
    assert _is_substantive_turn(
        SimpleNamespace(content="hi"), SimpleNamespace(text="ok"),
        SimpleNamespace(expert_findings=[object()], tool_calls=[]),
    )


# --- recall: the orchestrator can pull any earlier turn back verbatim (W8) -----

def _recall_tool():
    return next(t for t in build_orchestrator_tools([], []) if getattr(t, "__name__", "") == "recall")


def test_recall_tool_is_always_available():
    assert _recall_tool() is not None


def test_recall_returns_matching_earlier_turn_verbatim():
    recall = _recall_tool()
    transcript = [
        {"n": 1, "user": "my client is Acme Corp", "assistant": "noted, Acme it is"},
        {"n": 2, "user": "draft an outreach email", "assistant": "here is a draft"},
    ]
    ctx = SimpleNamespace(deps=SimpleNamespace(ctx=SimpleNamespace(session_transcript=transcript)))

    hit = asyncio.run(recall(ctx, "Acme"))
    assert "Turn 1" in hit and "Acme Corp" in hit                 # the full earlier turn, found by keyword

    miss = asyncio.run(recall(ctx, "nonexistent topic"))
    assert "no earlier turn" in miss.lower() and "2 earlier turn" in miss   # honest, with a count


def test_recall_with_no_history_is_a_safe_noop():
    recall = _recall_tool()
    ctx = SimpleNamespace(deps=SimpleNamespace(ctx=SimpleNamespace(session_transcript=[])))
    assert "no earlier turns" in asyncio.run(recall(ctx, "anything")).lower()
