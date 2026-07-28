"""
Cross-call workspace persistence — a `code.engineer` workspace surviving across a
mission's separate turns/calls, keyed on `(mission_id, expert_key)`. Ratified design:
proposals/archive/to-backend/2026-07-26_workspace-cross-call-persistence-design.md.

`ExpertHandler._snapshot_mission_workspace` (write side, called from `_run_one`'s
`finally` before the sandbox closes) and `_restore_mission_workspace` (read side,
called from the top of `_seed_inputs`) are exercised directly here — the same style
`tests/orchestrator_archive_extraction.py` already uses for `_seed_inputs`, since
driving a full `_run_one` needs a real expert + model stack that isn't the point of
this suite (the archive-validation core itself is `tests/workspace_archive.py`'s
job, once split out; here it's the mission-scoped snapshot/restore wiring).

Run:
    cd backend && .venv/bin/python -m pytest tests/orchestrator_workspace_persistence.py -v
"""

import asyncio
from types import SimpleNamespace as NS

from foundation import InputFile, ThreatLevel, VrakshaContext
from core.artifacts import LocalArtifactStore
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.workspace_transactions import _WORKSPACE_TRANSACTIONS
from registry.capabilities.handler.support import ExpertEnv, SkillBook


def _clean(monkeypatch):
    """A clean-scan double for `pre_sanitization.run` — restore re-scans every
    member (see `_restore_mission_workspace`'s docstring), and the real scanner
    needs a ClamAV daemon this environment doesn't have. Mirrors `tests/
    orchestrator_archive_extraction.py`'s own `_clean` helper."""
    async def fake_run(data):
        return NS(threat_level=ThreatLevel.NONE, reason=None)
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", fake_run)


class _FakeWorkspace:
    """An in-memory WorkspacePort stand-in supporting list/read_bytes/write_bytes —
    everything the snapshot/restore pair touches."""
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
    async def write_bytes(self, rel_path, data): self.files[rel_path] = data
    async def read_bytes(self, rel_path): return self.files[rel_path]
    async def list(self): return sorted(self.files)


def _env(ws):
    return ExpertEnv(module_dir=None, model_role="code", skills=SkillBook("/", ()),
                      toolbox=None, granted=[], workspace=ws)


def _ctx(mission_id: str = "m1") -> VrakshaContext:
    ctx = VrakshaContext.new("s")
    ctx.mission_id = mission_id
    return ctx


async def _transactional_update(
    handler,
    ctx,
    expert_key,
    filename,
    entered,
    release,
):
    """Exercise the restore → expert mutation → snapshot transaction from `_run_one`."""
    ws = _FakeWorkspace()
    env = _env(ws)
    async with handler._workspace_transaction(env, ctx, expert_key):
        await handler._seed_inputs(env, ctx, expert_key)
        entered.set()
        await release.wait()
        ws.files[filename] = filename.encode()
        await handler._snapshot_mission_workspace(expert_key, env, ctx)
    return ws.files


def test_same_workspace_key_serializes_the_production_lifecycle(tmp_path, monkeypatch):
    """A later call restores the first call's committed update before adding its own."""
    _clean(monkeypatch)

    async def prove():
        handler = ExpertHandler(artifact_store=LocalArtifactStore(base_dir=tmp_path))
        first_entered = asyncio.Event()
        second_entered = asyncio.Event()
        release_first = asyncio.Event()
        release_second = asyncio.Event()

        first = asyncio.create_task(_transactional_update(
            handler, _ctx(), "code.engineer", "first.py",
            first_entered, release_first,
        ))
        await first_entered.wait()
        second = asyncio.create_task(_transactional_update(
            handler, _ctx(), "code.engineer", "second.py",
            second_entered, release_second,
        ))

        release_first.set()
        await first
        await asyncio.wait_for(second_entered.wait(), timeout=1)
        release_second.set()
        assert await second == {
            "first.py": b"first.py",
            "second.py": b"second.py",
        }

        restored = _FakeWorkspace()
        await handler._restore_mission_workspace(restored, _ctx(), "code.engineer")
        assert restored.files == {
            "first.py": b"first.py",
            "second.py": b"second.py",
        }

    asyncio.run(prove())


def test_different_workspace_keys_are_not_globally_serialized(tmp_path, monkeypatch):
    """Mission and expert are both part of the lock key."""
    _clean(monkeypatch)

    async def prove_pair(left_ctx, left_expert, right_ctx, right_expert):
        handler = ExpertHandler(artifact_store=LocalArtifactStore(base_dir=tmp_path))
        left_entered = asyncio.Event()
        right_entered = asyncio.Event()
        release = asyncio.Event()
        left = asyncio.create_task(_transactional_update(
            handler, left_ctx, left_expert, "left.py", left_entered, release,
        ))
        await left_entered.wait()
        right = asyncio.create_task(_transactional_update(
            handler, right_ctx, right_expert, "right.py", right_entered, release,
        ))

        # This event is set only from inside the transaction while the first key
        # is still held. A global lock therefore cannot satisfy the assertion.
        await asyncio.wait_for(right_entered.wait(), timeout=1)
        release.set()
        await asyncio.gather(left, right)

    async def prove():
        await prove_pair(_ctx("mission-a"), "code.engineer",
                         _ctx("mission-b"), "code.engineer")
        await prove_pair(_ctx("mission-c"), "code.engineer",
                         _ctx("mission-c"), "some.other.expert")

    asyncio.run(prove())


def test_cancelled_and_failed_transactions_release_the_key(tmp_path):
    async def prove():
        handler = ExpertHandler(artifact_store=LocalArtifactStore(base_dir=tmp_path))
        ctx = _ctx()
        env = _env(_FakeWorkspace())

        entered = asyncio.Event()
        never_release = asyncio.Event()

        async def cancelled_call():
            async with handler._workspace_transaction(env, ctx, "code.engineer"):
                entered.set()
                await never_release.wait()

        task = asyncio.create_task(cancelled_call())
        await entered.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        try:
            async with handler._workspace_transaction(env, ctx, "code.engineer"):
                raise RuntimeError("controlled expert failure")
        except RuntimeError:
            pass

        later_entered = asyncio.Event()
        async with handler._workspace_transaction(env, ctx, "code.engineer"):
            later_entered.set()
        assert later_entered.is_set()

    asyncio.run(prove())


def test_workspace_transaction_registry_drops_idle_keys(tmp_path):
    async def prove():
        handler = ExpertHandler(artifact_store=LocalArtifactStore(base_dir=tmp_path))
        assert _WORKSPACE_TRANSACTIONS._locks == {}
        for index in range(50):
            ctx = _ctx(f"mission-{index}")
            async with handler._workspace_transaction(
                _env(_FakeWorkspace()), ctx, f"expert-{index}",
            ):
                pass
        assert _WORKSPACE_TRANSACTIONS._locks == {}

    asyncio.run(prove())


def test_snapshot_is_a_noop_outside_a_mission(tmp_path):
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws = _FakeWorkspace({"a.py": b"x = 1\n"})
    env = _env(ws)
    ctx = VrakshaContext.new("s")   # mission_id == "" — the ordinary chat-turn case
    asyncio.run(handler._snapshot_mission_workspace("code.engineer", env, ctx))
    assert list(tmp_path.iterdir()) == []   # nothing at all written to the store
    assert ctx.tool_calls == []


def test_restore_is_a_silent_noop_on_a_missions_first_call(tmp_path):
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws = _FakeWorkspace()
    ctx = _ctx()
    asyncio.run(handler._restore_mission_workspace(ws, ctx, "code.engineer"))
    assert ws.files == {} and ctx.tool_calls == []   # no snapshot yet -> not an error


def test_snapshot_then_restore_round_trips_the_workspace(tmp_path, monkeypatch):
    _clean(monkeypatch)
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)

    # call 1: code.engineer writes a repo, its workspace snapshots on close
    ws1 = _FakeWorkspace({"src/main.py": b"print('hi')\n", "README.md": b"# repo\n"})
    ctx1 = _ctx()
    asyncio.run(handler._snapshot_mission_workspace("code.engineer", _env(ws1), ctx1))

    # call 2: same mission, same expert, a FRESH empty workspace (as _run_one always
    # hands a brand-new DockerWorkspace) -- restore must repopulate it before anything else
    ws2 = _FakeWorkspace()
    ctx2 = _ctx()
    asyncio.run(handler._restore_mission_workspace(ws2, ctx2, "code.engineer"))
    assert ws2.files == {"src/main.py": b"print('hi')\n", "README.md": b"# repo\n"}
    assert ctx2.tool_calls[0].success is True
    assert ctx2.tool_calls[0].result == {"files_restored": 2}


def test_restore_is_scoped_by_expert_key_not_just_mission(tmp_path, monkeypatch):
    _clean(monkeypatch)
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws1 = _FakeWorkspace({"a.py": b"x\n"})
    ctx1 = _ctx()
    asyncio.run(handler._snapshot_mission_workspace("code.engineer", _env(ws1), ctx1))

    ws2 = _FakeWorkspace()
    ctx2 = _ctx()
    asyncio.run(handler._restore_mission_workspace(ws2, ctx2, "some.other.expert"))
    assert ws2.files == {}   # a different expert key never sees code.engineer's snapshot


def test_seed_inputs_restores_before_handling_fresh_files(tmp_path, monkeypatch):
    """The end-to-end wiring: _seed_inputs (not the private restore method directly)
    on a mission's SECOND call, with no archive upload of its own, restores the
    prior snapshot as the workspace's starting state."""
    _clean(monkeypatch)
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws1 = _FakeWorkspace({"repo/lib.py": b"x = 1\n"})
    ctx1 = _ctx()
    asyncio.run(handler._snapshot_mission_workspace("code.engineer", _env(ws1), ctx1))

    ws2 = _FakeWorkspace()
    ctx2 = _ctx()   # no ctx2.input_files this call -- a "continue the work" turn
    asyncio.run(handler._seed_inputs(_env(ws2), ctx2, "code.engineer"))
    assert ws2.files == {"repo/lib.py": b"x = 1\n"}


def test_fresh_archive_upload_skips_restore_and_wins_outright(tmp_path, monkeypatch):
    import io
    import zipfile

    def _zip(members: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return buf.getvalue()

    _clean(monkeypatch)
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws1 = _FakeWorkspace({"old/stale.py": b"x = 1\n"})
    ctx1 = _ctx()
    asyncio.run(handler._snapshot_mission_workspace("code.engineer", _env(ws1), ctx1))

    ws2 = _FakeWorkspace()
    ctx2 = _ctx()
    data = _zip({"new/fresh.py": b"y = 2\n"})
    ctx2.input_files = [InputFile("repo.zip", "archive", data, len(data))]
    asyncio.run(handler._seed_inputs(_env(ws2), ctx2, "code.engineer"))
    # only the fresh upload's file is present -- the stale snapshot was never restored
    assert ws2.files == {"new/fresh.py": b"y = 2\n"}


def test_oversized_workspace_skips_the_snapshot_with_an_honest_note(tmp_path, monkeypatch):
    import settings
    tight = settings.SECURITY.model_copy(update={"max_workspace_snapshot_bytes": 4})
    monkeypatch.setattr(settings, "SECURITY", tight)   # 4 bytes, smaller than the file below
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    ws = _FakeWorkspace({"big.py": b"x" * 100})
    ctx = _ctx()
    asyncio.run(handler._snapshot_mission_workspace("code.engineer", _env(ws), ctx))
    assert asyncio.run(store.list("mission-m1-code.engineer")) == []   # nothing persisted
    assert ctx.tool_calls[0].success is False
    assert "snapshot cap" in ctx.tool_calls[0].error


def test_corrupted_snapshot_fails_closed_not_a_crash(tmp_path):
    store = LocalArtifactStore(base_dir=tmp_path)
    handler = ExpertHandler(artifact_store=store)
    asyncio.run(store.put("mission-m1-code.engineer", "_workspace.zip", b"not a zip"))
    ws = _FakeWorkspace()
    ctx = _ctx()
    asyncio.run(handler._restore_mission_workspace(ws, ctx, "code.engineer"))
    assert ws.files == {}
    assert ctx.tool_calls[0].success is False
