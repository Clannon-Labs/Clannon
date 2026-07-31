"""Post-delivery lifecycle hands neutral evidence to Memory Manager only."""

import asyncio

from foundation import Flow, NormalizedInput
import core.memory.lifecycle as lifecycle


def _flow():
    normalized = NormalizedInput(
        modality="text", content_type="text/plain", content="Remember our Acme format."
    )
    flow = Flow.new(normalized, "session-1", user_id="user-1", trace_id="trace-1")
    flow.ctx.normalized_input = normalized
    flow.ctx.final_response = "Acme reports use a one-page executive format."
    return flow


def test_lifecycle_builds_neutral_turn_without_tier_or_write_proposal():
    turn = lifecycle._turn(_flow().ctx)
    assert turn is not None
    assert turn.user_id == "user-1"
    assert turn.session_id == "session-1"
    assert turn.trace_id == "trace-1"
    assert turn.request.startswith("Remember")
    assert turn.response.startswith("Acme reports")
    assert not hasattr(turn, "store")
    assert not hasattr(turn, "tier")


def test_lifecycle_calls_manager_after_delivery(monkeypatch):
    seen = []

    async def process_turn(turn):
        seen.append(turn)
        return []

    monkeypatch.setattr(lifecycle.manager, "process_turn", process_turn)

    async def go():
        await lifecycle.run(_flow())
        await asyncio.gather(*tuple(lifecycle._BACKGROUND))

    asyncio.run(go())
    assert len(seen) == 1
    assert seen[0].user_id == "user-1"


def test_lifecycle_skips_incomplete_turn(monkeypatch):
    seen = []

    async def process_turn(turn):
        seen.append(turn)
        return []

    monkeypatch.setattr(lifecycle.manager, "process_turn", process_turn)
    flow = _flow()
    flow.ctx.final_response = None

    asyncio.run(lifecycle.run(flow))
    assert seen == []


def test_lifecycle_fault_never_fails_delivered_turn(monkeypatch):
    async def process_turn(turn):
        raise RuntimeError("curator unavailable")

    monkeypatch.setattr(lifecycle.manager, "process_turn", process_turn)

    async def go():
        out = await lifecycle.run(_flow())
        await asyncio.gather(*tuple(lifecycle._BACKGROUND))
        return out

    out = asyncio.run(go())
    assert not out.ctx.failed
    assert out.ctx.final_response
