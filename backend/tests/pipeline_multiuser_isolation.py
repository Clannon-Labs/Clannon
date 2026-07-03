"""
Hermetic harness: pipeline/orchestrator-level tenant isolation under concurrency.

Drives TWO distinct user_ids through the REAL pipeline.run() (normalizer ->
hydration_prefetch -> verifier -> orchestrator -> filter -> delivery) concurrently
via asyncio.gather, with hermetic test doubles for every LLM and store call.
Asserts:

  1. No cross-user bleed: each user's hydrated memory, decision-log entries,
     final report, and per-run ctx never contain the other user's fingerprinted data.
  2. Memory reads are scoped to each run's own user_id (the store double is keyed
     by the user_id field of the HydrationRequest, mirroring the real Qdrant filter).
  3. An empty/missing user_id run fails closed: the run completes with empty
     hydration_items and never borrows context from another user's memory.

The LLM double is wired at the Capabilities.run_turn seam so the REAL run_loop
executes, including _hydrate() (which populates ctx.hydration_items from the
prefetched future) and the on_message/on_event emitters (which populate
ctx.decision_log via CtxDecisionLog.emit). The harness asserts that both
hydration_items and decision_log are NON-EMPTY before checking that they carry no
foreign-user fingerprints, preventing those assertions from passing vacuously on
an empty collection.

Pins Critical Benchmark 5 (security/memory-isolation guarantee) and Critical
Benchmark 6 (multi-agent consistency contract) at the orchestration layer, above
the memory-door read-scope test that covers the Qdrant user_id payload filter.

This file is ADDITIVE: no pipeline, orchestrator, memory, or scoping logic is
changed. All LLM and store I/O is replaced by hermetic test doubles (no network,
no paid API keys). The store double is keyed by the user_id payload field, exactly
mirroring the real Qdrant filter.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from foundation import (
    HydrationPackage,
    MemoryItem,
    MemoryStore,
)
from core.orchestrator.schemas import OrchestratorAnswer
from core.pipeline import ACTIVE_STAGES, run as pipeline_run
from core.verifier.utils import verification_result
import core.verifier.verifier as verifier_mod
import security.filter.filter as filter_mod
from security.filter.schemas import FilterResult


# ---------------------------------------------------------------------------
# Per-user fingerprints -- unique strings that must never cross user boundaries
# ---------------------------------------------------------------------------

_UID_A = "user_alpha"
_UID_B = "user_beta"

_MEM_A = "ALPHA_MEM_PRIVATE"   # embedded in alpha's memory items
_MEM_B = "BETA_MEM_PRIVATE"    # embedded in beta's memory items
_RPT_A = "ALPHA_REPORT_TAG"    # embedded in alpha's synthesised report
_RPT_B = "BETA_REPORT_TAG"     # embedded in beta's synthesised report


# ---------------------------------------------------------------------------
# Slim stage list -- normalizer onwards, skipping intake + sanitizer
# (both need a live ClamAV daemon; the scope of this test is orchestration-level)
# ---------------------------------------------------------------------------

_SLIM_STAGES = [s for s in ACTIVE_STAGES if s.name not in ("intake", "sanitizer")]


# ---------------------------------------------------------------------------
# Test-double MemoryPort
# Keyed by user_id: returns a fingerprinted item per known user, an empty
# package for an empty user_id (fail-closed), and an empty package for any
# unrecognised user. An asyncio.sleep(0) inside each hydrate call yields the
# event loop, guaranteeing true interleaving when two users run concurrently.
# ---------------------------------------------------------------------------

class _TrackingMemory:
    def __init__(self) -> None:
        self.hydrate_calls: list[tuple[str, str]] = []   # (user_id, item_content)
        self.write_calls: list[tuple[str, int]] = []      # (user_id, proposal_count)

    async def hydrate(self, req) -> HydrationPackage:
        await asyncio.sleep(0)          # yield -- forces real interleaving under gather
        uid = req.user_id
        if not uid:
            # fail-closed: no scope -> no memory; never borrow another user's data
            return HydrationPackage(notes="no user scope; memory skipped")
        if uid == _UID_A:
            tag, content = _MEM_A, f"{_MEM_A}:data_for_{uid}"
        elif uid == _UID_B:
            tag, content = _MEM_B, f"{_MEM_B}:data_for_{uid}"
        else:
            # unknown user: empty (safe default; does not emit a fingerprint)
            return HydrationPackage(notes=f"no memory for {uid!r}")
        self.hydrate_calls.append((uid, content))
        return HydrationPackage(items=[
            MemoryItem(
                store=MemoryStore.EPISODIC,
                content=content,
                score=0.9,
                trust=1,
                created_at=0.0,
            )
        ])

    async def record_write_proposals(
        self, user_id: str, session_id: str, proposals: list
    ) -> None:
        self.write_calls.append((user_id, len(proposals)))

    async def learn(
        self, user_id: str, session_id: str,
        *, task: str, answer: str, findings: list
    ) -> None:
        pass  # best-effort background distillation; hermetic no-op


# ---------------------------------------------------------------------------
# Wire all test doubles into the pipeline modules
# ---------------------------------------------------------------------------

def _wire_doubles(monkeypatch, mem: _TrackingMemory) -> None:
    # verifier: always proceed (no LLM call)
    async def _fake_verify(normalized, deterministic):
        return verification_result(proceed=True, normalized=normalized)
    monkeypatch.setattr(verifier_mod, "verify_with_llm", _fake_verify)

    # capability gateway: patch Capabilities.run_turn so the REAL run_loop
    # executes. The real run_loop calls _hydrate() (which awaits the
    # prefetched future and sets ctx.hydration_items) and passes on_message
    # and on_event closures to run_turn. By calling on_message here with the
    # per-user tag, we cause run_loop's on_message closure to emit a real
    # DecisionLogEntry onto ctx.decision_log via CtxDecisionLog.emit. The
    # run_loop also emits an "answer" entry after run_turn returns, so
    # ctx.decision_log is guaranteed non-empty for every real user run.
    import registry.capabilities.handler.capability as caps_mod

    async def _fake_run_turn(
        self, *, system_prompt, user_prompt, output_type,
        on_event=None, on_message=None, **kwargs
    ):
        await asyncio.sleep(0)   # yield -- forces true interleaving under gather
        uid = self.ctx.user_id
        if uid == _UID_A:
            tag = _RPT_A
        elif uid == _UID_B:
            tag = _RPT_B
        else:
            tag = f"REPORT_TAG_{uid}"
        if on_message:
            await on_message(f"Synthesizing report. {tag}")
        return OrchestratorAnswer(
            answer_text=f"Synthesis complete. {tag}", confidence=0.9
        )

    monkeypatch.setattr(caps_mod.Capabilities, "run_turn", _fake_run_turn)

    # output filter: always proceed (no LLM call)
    async def _fake_filter(response, findings, memory, tool_calls):
        return FilterResult(proceed=True)
    monkeypatch.setattr(filter_mod, "_filter", _fake_filter)

    # memory singleton: replace methods with tracking stubs so no Qdrant or
    # embedding call is made, while the user_id scoping logic stays intact.
    import core.memory as _core_mem
    monkeypatch.setattr(_core_mem.manager, "hydrate", mem.hydrate)
    monkeypatch.setattr(_core_mem.manager, "record_write_proposals", mem.record_write_proposals)
    monkeypatch.setattr(_core_mem.manager, "learn", mem.learn)


# ---------------------------------------------------------------------------
# Helpers -- extract text representations for bleed checks
# ---------------------------------------------------------------------------

def _item_texts(flow) -> list[str]:
    return [getattr(i, "content", str(i)) for i in flow.ctx.hydration_items]


def _dlog_text(flow) -> str:
    return " ".join(getattr(e, "message", str(e)) for e in flow.ctx.decision_log)


def _report_text(flow) -> str:
    return flow.ctx.final_response or ""


def _collect_bleed(
    flow,
    own_mem: str,
    own_rpt: str,
    foreign_mem: str,
    foreign_rpt: str,
) -> list[str]:
    """Return a list of bleed observations (empty list = clean)."""
    findings: list[str] = []
    items = _item_texts(flow)
    report = _report_text(flow)
    dlog = _dlog_text(flow)

    for i, content in enumerate(items):
        if foreign_mem in content:
            findings.append(
                f"hydration_items[{i}] contains foreign tag {foreign_mem!r}: {content!r}"
            )

    if foreign_rpt in report:
        findings.append(f"final_response contains foreign tag {foreign_rpt!r}: {report!r}")

    if foreign_mem in dlog:
        findings.append(f"decision_log contains foreign mem tag {foreign_mem!r}")
    if foreign_rpt in dlog:
        findings.append(f"decision_log contains foreign rpt tag {foreign_rpt!r}")

    return findings


# ---------------------------------------------------------------------------
# Isolation table printer
# ---------------------------------------------------------------------------

def _print_table(
    rows: list[tuple[str, bool, bool, bool, bool, list[str]]],
) -> None:
    """Print a per-user state-vs-cross-leak summary table.

    Columns: user | user_id | memory | report | dlog | verdict
    """
    sep = "-" * 72
    header = (
        f"{'User':<20} {'user_id':^10} {'memory':^10}"
        f" {'report':^10} {'dlog':^10} {'verdict':^10}"
    )
    print()
    print("=" * 72)
    print("Pipeline Multi-User Isolation  (hermetic, asyncio.gather interleaved)")
    print("=" * 72)
    print(header)
    print(sep)
    for uid, uid_ok, mem_ok, rpt_ok, dlog_ok, bleed in rows:
        verdict = "SCOPED" if not bleed else "BLEED"
        print(
            f"{uid:<20} {'OK' if uid_ok else 'FAIL':^10} "
            f"{'OK' if mem_ok else 'FAIL':^10} "
            f"{'OK' if rpt_ok else 'FAIL':^10} "
            f"{'OK' if dlog_ok else 'FAIL':^10} "
            f"{verdict:^10}"
        )
        for detail in bleed:
            print(f"  ! {detail}")
    print(sep)


# ---------------------------------------------------------------------------
# Needs-reviewer note writer (only invoked on genuine bleed)
# ---------------------------------------------------------------------------

def _open_reviewer_note(bleeds: list[str], context: str) -> None:
    note = {
        "kind": "needs-reviewer",
        "title": "SECURITY: cross-user bleed at pipeline/orchestrator layer",
        "test": "backend/tests/pipeline_multiuser_isolation.py",
        "context": context,
        "findings": bleeds,
        "action": (
            "Genuine cross-user data bleed detected. Audit ctx sharing, "
            "hydration_future propagation, and memory singleton scoping. "
            "DO NOT merge any open PR until this is resolved."
        ),
    }
    dest = pathlib.Path("/home/amrit/.clannon_proposal")
    try:
        dest.write_text(json.dumps(note, indent=2))
    except OSError:
        pass  # best-effort; the pytest failure carries the findings


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_two_user_concurrent_isolation(monkeypatch):
    """Two concurrent pipeline runs share no ctx, memory items, report, or decision-log.

    asyncio.gather interleaves the two coroutines on a single event loop. The
    asyncio.sleep(0) yields inside each test double guarantee that run A and run B
    are actually in flight simultaneously, so any shared-state bug would surface.

    The Capabilities.run_turn double calls on_message with the per-user tag so that
    the REAL run_loop emits real DecisionLogEntry objects onto ctx.decision_log. The
    REAL _hydrate() awaits the prefetched future and sets ctx.hydration_items from
    the store double. Both collections are asserted NON-EMPTY before checking
    isolation, so neither assertion can pass vacuously on an empty collection.
    """
    mem = _TrackingMemory()
    _wire_doubles(monkeypatch, mem)

    async def _run_both():
        return await asyncio.gather(
            pipeline_run(
                f"Research brief for {_UID_A}",
                f"sess_{_UID_A}",
                user_id=_UID_A,
                stages=_SLIM_STAGES,
            ),
            pipeline_run(
                f"Research brief for {_UID_B}",
                f"sess_{_UID_B}",
                user_id=_UID_B,
                stages=_SLIM_STAGES,
            ),
        )

    flow_a, flow_b = asyncio.run(_run_both())

    # -- identity: each ctx must carry its own user_id (set once at intake) ----
    assert flow_a.ctx.user_id == _UID_A, (
        f"flow_a.ctx.user_id is {flow_a.ctx.user_id!r}, expected {_UID_A!r}"
    )
    assert flow_b.ctx.user_id == _UID_B, (
        f"flow_b.ctx.user_id is {flow_b.ctx.user_id!r}, expected {_UID_B!r}"
    )

    # -- memory scope: the store double was queried with each user's own id -----
    call_map: dict[str, list[str]] = {}
    for uid, content in mem.hydrate_calls:
        call_map.setdefault(uid, []).append(content)

    assert _UID_A in call_map, "memory.hydrate was never called for user_alpha"
    assert _UID_B in call_map, "memory.hydrate was never called for user_beta"

    for content in call_map.get(_UID_A, []):
        assert _MEM_B not in content, (
            f"alpha's memory query returned beta-fingerprinted content: {content!r}"
        )
    for content in call_map.get(_UID_B, []):
        assert _MEM_A not in content, (
            f"beta's memory query returned alpha-fingerprinted content: {content!r}"
        )

    # -- hydration_items: non-empty, and each run carries only its own fingerprint
    a_items = _item_texts(flow_a)
    b_items = _item_texts(flow_b)

    assert len(a_items) >= 1, (
        "user_alpha hydration_items is empty -- the store double should have "
        "returned one fingerprinted item for this user"
    )
    assert len(b_items) >= 1, (
        "user_beta hydration_items is empty -- the store double should have "
        "returned one fingerprinted item for this user"
    )
    for content in a_items:
        assert _MEM_B not in content, (
            f"user_alpha.hydration_items contains beta fingerprint: {content!r}"
        )
    for content in b_items:
        assert _MEM_A not in content, (
            f"user_beta.hydration_items contains alpha fingerprint: {content!r}"
        )

    # -- report: each report carries only its own fingerprint ------------------
    rpt_a = _report_text(flow_a)
    rpt_b = _report_text(flow_b)

    assert _RPT_B not in rpt_a, (
        f"user_alpha final_response contains beta tag: {rpt_a!r}"
    )
    assert _RPT_A not in rpt_b, (
        f"user_beta final_response contains alpha tag: {rpt_b!r}"
    )

    # -- decision log: non-empty, and no foreign fingerprints in either run ----
    dlog_a = _dlog_text(flow_a)
    dlog_b = _dlog_text(flow_b)

    assert len(flow_a.ctx.decision_log) >= 1, (
        "user_alpha decision_log is empty -- run_loop should have emitted at "
        "least one entry via on_message + the answer entry"
    )
    assert len(flow_b.ctx.decision_log) >= 1, (
        "user_beta decision_log is empty -- run_loop should have emitted at "
        "least one entry via on_message + the answer entry"
    )
    assert _MEM_B not in dlog_a and _RPT_B not in dlog_a, (
        f"user_alpha decision_log contains beta data: {dlog_a!r}"
    )
    assert _MEM_A not in dlog_b and _RPT_A not in dlog_b, (
        f"user_beta decision_log contains alpha data: {dlog_b!r}"
    )

    # -- collect bleed observations and print the isolation table ---------------
    bleed_a = _collect_bleed(flow_a, _MEM_A, _RPT_A, _MEM_B, _RPT_B)
    bleed_b = _collect_bleed(flow_b, _MEM_B, _RPT_B, _MEM_A, _RPT_A)

    _print_table([
        (
            _UID_A,
            flow_a.ctx.user_id == _UID_A,
            len(a_items) >= 1 and all(_MEM_B not in c for c in a_items),
            _RPT_B not in rpt_a,
            len(flow_a.ctx.decision_log) >= 1 and _MEM_B not in dlog_a and _RPT_B not in dlog_a,
            bleed_a,
        ),
        (
            _UID_B,
            flow_b.ctx.user_id == _UID_B,
            len(b_items) >= 1 and all(_MEM_A not in c for c in b_items),
            _RPT_A not in rpt_b,
            len(flow_b.ctx.decision_log) >= 1 and _MEM_A not in dlog_b and _RPT_A not in dlog_b,
            bleed_b,
        ),
    ])

    # -- escalate if genuine bleed: write a reviewer note then fail the test ----
    all_bleeds = bleed_a + bleed_b
    if all_bleeds:
        _open_reviewer_note(
            all_bleeds,
            "two real user_ids interleaved via asyncio.gather on a single event loop",
        )
        pytest.fail(
            f"Cross-user bleed: {len(all_bleeds)} finding(s). "
            "Reviewer note written to ~/.clannon_proposal. See table above."
        )


def test_empty_user_id_fails_closed(monkeypatch):
    """An empty user_id run completes but receives NO memory -- never borrows context.

    Confirms the fail-closed scoping rule (invariant V.20, ADR 0002) at the
    orchestration layer: missing identity => empty hydration_items, not a
    borrowed slice of another user's memory.

    The real _hydrate() runs under the new seam (Capabilities.run_turn is doubled,
    not run_loop), so ctx.hydration_items == [] is now a genuine observation of
    the hydration path returning an empty package for the empty user_id scope,
    not a vacuous assertion on state that was never populated.
    """
    mem = _TrackingMemory()
    _wire_doubles(monkeypatch, mem)

    flow = asyncio.run(
        pipeline_run(
            "Unscoped brief with no identity",
            "sess_anon",
            user_id="",
            stages=_SLIM_STAGES,
        )
    )

    # run must not crash (empty scope is degraded, not a hard failure)
    assert not flow.ctx.failed, (
        f"empty user_id run raised an unexpected failure: {flow.ctx.failure_error}"
    )

    # no memory items: empty scope returns an empty package, never borrows data
    assert flow.ctx.hydration_items == [], (
        f"empty user_id received non-empty hydration_items: {flow.ctx.hydration_items!r}"
    )

    # memory.hydrate must not have been called with a real (non-empty) user_id
    non_empty_hydrate_calls = [(u, c) for u, c in mem.hydrate_calls if u]
    assert not non_empty_hydrate_calls, (
        f"hydrate was called with a real user_id during an empty-scope run: "
        f"{non_empty_hydrate_calls!r}"
    )

    # print the empty-scope row in the same table format for completeness
    _print_table([
        (
            "(empty user_id)",
            flow.ctx.user_id == "",
            flow.ctx.hydration_items == [],
            True,   # no foreign fingerprint possible in an empty-scope run
            True,
            [],     # no bleed by definition: no foreign user_id was active
        ),
    ])
    print(f"  hydration_items: {flow.ctx.hydration_items!r}  (empty = scoped)")
    print(f"  non-empty hydrate calls: {non_empty_hydrate_calls!r}  (none = scoped)")
    print(f"  verdict: SCOPED (fail-closed on missing identity)")
