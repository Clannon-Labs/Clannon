"""
Archive-into-workspace extraction — the CB2 real-repo-input track.

`security/sanitizers/uploads.py` (backend's tree) admits a zip past a cheap,
metadata-only Layer-1 bomb precheck; `ExpertHandler._seed_inputs`/`_extract_archive`
(`registry/capabilities/handler/experts.py`, this tree) is the authoritative,
byte-verified guard at extraction time — see the ratified design:
proposals/archive/to-backend/2026-07-25_nav-patch-tooling-design.md §3.

All-or-nothing: any cap breach, unsafe member path, or malware hit on ANY member
rejects the WHOLE archive, nothing written — and the rejection is never silent:
`env.seed_failures` carries (name, reason) for the expert's own prompt, and
`ctx.tool_calls` carries an audit record for the trace/decision log.

Local fixture copies (`_zip_bytes`/`_RecordingWS`/`_env`) deliberately mirror
`tests/uploads.py` rather than importing from it — that file is backend's tree
(security's archive-admission tests + the pre-existing plain-file seed tests);
this one stays entirely in orchestration's own tree per the ownership boundary
in this module's CLAUDE.md.

Run:
    cd backend && .venv/bin/python -m pytest tests/orchestrator_archive_extraction.py -v
"""

import asyncio
import io
import zipfile
from types import SimpleNamespace as NS

import settings
from foundation import InputFile, ThreatLevel, VrakshaContext
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.sandbox import DockerWorkspace
from registry.capabilities.handler.support import ExpertEnv, SkillBook


def _zip_bytes(members: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _archive_input(members: dict[str, bytes]) -> InputFile:
    data = _zip_bytes(members)
    return InputFile("repo.zip", "archive", data, len(data))


def _clean(monkeypatch):
    async def fake_run(data):
        return NS(threat_level=ThreatLevel.NONE, reason=None)
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", fake_run)


class _RecordingWS:
    """Workspace stand-in that records seeded files."""
    def __init__(self):
        self.files = {}
    async def write_bytes(self, rel, data):
        self.files[rel] = data


def _env(ws):
    return ExpertEnv(module_dir=None, model_role="code", skills=SkillBook("/", ()),
                     toolbox=None, granted=[], workspace=ws)


def test_seed_inputs_extracts_archive_members_into_the_workspace(monkeypatch):
    _clean(monkeypatch)
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"src/main.py": b"print('hi')\n", "README.md": b"# repo\n"})]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {"src/main.py": b"print('hi')\n", "README.md": b"# repo\n"}
    assert sorted(env.input_files) == ["README.md", "src/main.py"]
    assert env.seed_failures == []


def test_seed_inputs_archive_skips_directory_entries(monkeypatch):
    _clean(monkeypatch)
    data = _zip_bytes({"src/": b"", "src/main.py": b"x = 1\n"})
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [InputFile("repo.zip", "archive", data, len(data))]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {"src/main.py": b"x = 1\n"}


def test_seed_inputs_archive_rejects_whole_archive_on_a_malicious_member(monkeypatch):
    async def fake_run(data):
        if data == b"evil":
            return NS(threat_level=ThreatLevel.HIGH, reason="ClamAV: Eicar-Test-Signature")
        return NS(threat_level=ThreatLevel.NONE, reason=None)
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", fake_run)
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"clean.txt": b"hello", "bad.txt": b"evil"})]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    # all-or-nothing: the clean member is NOT written just because it scanned first
    assert ws.files == {} and env.input_files == []
    # and it's not a SILENT miss: the expert's own env carries why, and it's audited
    assert len(env.seed_failures) == 1
    name, reason = env.seed_failures[0]
    assert name == "repo.zip" and "security scan" in reason
    assert len(ctx.tool_calls) == 1
    assert ctx.tool_calls[0].tool_name == "fs.seed_input" and ctx.tool_calls[0].success is False


def test_seed_inputs_archive_rejects_when_entry_count_exceeds_the_floor(monkeypatch):
    _clean(monkeypatch)
    tight = settings.SECURITY.model_copy(update={"archive_max_entries": 1})
    monkeypatch.setattr("registry.capabilities.handler.experts.settings.SECURITY", tight)
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"a.txt": b"one", "b.txt": b"two"})]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {} and env.input_files == []
    assert "entries" in env.seed_failures[0][1]


def test_seed_inputs_archive_rejects_a_member_over_the_per_member_cap(monkeypatch):
    _clean(monkeypatch)
    tight = settings.INTAKE.model_copy(update={"max_input_size_bytes": 4})
    monkeypatch.setattr("registry.capabilities.handler.experts.settings.INTAKE", tight)
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"big.txt": b"way too long for the cap"})]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {} and env.input_files == []
    assert "per-file cap" in env.seed_failures[0][1]


def test_seed_inputs_archive_rejects_a_decompression_bomb_by_ratio(monkeypatch):
    _clean(monkeypatch)
    tight = settings.SECURITY.model_copy(update={"archive_max_uncompressed_ratio": 2})
    monkeypatch.setattr("registry.capabilities.handler.experts.settings.SECURITY", tight)
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    # highly compressible -> tiny compressed archive, large actual decompressed bytes,
    # byte-verified (read off the member, not trusting the zip's own declared size)
    ctx.input_files = [_archive_input({"huge.bin": b"\x00" * 200_000})]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {} and env.input_files == []
    assert "bomb-guard" in env.seed_failures[0][1]


def test_seed_inputs_archive_rejects_a_zip_slip_member_path(monkeypatch):
    _clean(monkeypatch)
    # graft an unsafe member name onto an otherwise-valid zip, past writestr's own
    # normalization, to prove the pre-write path check actually fires
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("safe.txt", "ok")
        info = zipfile.ZipInfo("../../etc/evil.txt")
        zf.writestr(info, "pwned")
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [InputFile("repo.zip", "archive", buf.getvalue(), len(buf.getvalue()))]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {} and env.input_files == []
    assert "unsafe path" in env.seed_failures[0][1]


def test_seed_inputs_archive_corrupt_zip_seeds_nothing(monkeypatch):
    _clean(monkeypatch)
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [InputFile("repo.zip", "archive", b"not a real zip", 14)]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {} and env.input_files == []
    assert "not a valid zip" in env.seed_failures[0][1]


def test_seed_inputs_archive_extracts_onto_the_real_workspace(monkeypatch):
    # proves the extraction path against the REAL DockerWorkspace.write_bytes ->
    # _resolve confinement, not just the recording stand-in — file I/O needs no
    # Docker container
    _clean(monkeypatch)
    ws = DockerWorkspace()
    try:
        env = _env(ws)
        ctx = VrakshaContext.new("s")
        ctx.input_files = [_archive_input({"src/main.py": b"print('hi')\n", "README.md": b"# repo\n"})]
        asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
        assert asyncio.run(ws.read_bytes("src/main.py")) == b"print('hi')\n"
        assert asyncio.run(ws.read_bytes("README.md")) == b"# repo\n"
        assert sorted(env.input_files) == ["README.md", "src/main.py"]
    finally:
        asyncio.run(ws.close())


def test_input_files_note_bounds_a_large_member_listing_and_surfaces_failures():
    from registry.capabilities.handler.support import _input_files_note, _MAX_LISTED_INPUT_FILES

    env = _env(_RecordingWS())
    env.input_files = [f"src/file_{i}.py" for i in range(_MAX_LISTED_INPUT_FILES + 10)]
    note = _input_files_note(env)
    assert f"and 10 more" in note
    assert note.count("src/file_") == _MAX_LISTED_INPUT_FILES

    env2 = _env(_RecordingWS())
    env2.seed_failures = [("repo.zip", "entries exceed the cap")]
    note2 = _input_files_note(env2)
    assert "could NOT be placed" in note2 and "repo.zip (entries exceed the cap)" in note2


def test_seed_inputs_archive_with_only_directory_entries_is_an_honest_miss(monkeypatch):
    _clean(monkeypatch)
    data = _zip_bytes({"empty_dir/": b""})
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [InputFile("repo.zip", "archive", data, len(data))]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx, "code.engineer"))
    assert ws.files == {} and env.input_files == []
    assert "no file members" in env.seed_failures[0][1]


def test_record_seed_fault_backfills_env_and_the_audit_trail():
    # unit-level: proves the backfill mechanics `_record_seed_fault` performs
    # once a seed attempt is cut short (its own env.input_files/seed_failures
    # writes never happened) -- the WIRING that actually reaches this from a
    # real expert run is proved separately below, driving _run_one for real
    env = _env(_RecordingWS())
    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"a.txt": b"hi"})]
    ExpertHandler()._record_seed_fault(env, ctx)
    assert env.input_files == []
    assert env.seed_failures == [("repo.zip", "input seeding timed out")]
    assert any(c.tool_name == "fs.seed_input" and "timed out" in (c.error or "") for c in ctx.tool_calls)


def test_run_one_degrades_honestly_when_seed_inputs_times_out(monkeypatch):
    # drives the REAL _run_one (via run_experts, the public entry point) with a
    # hung scanner, proving the asyncio.wait_for wrapping in _run_one is actually
    # wired -- a test that only calls _record_seed_fault directly (see above)
    # would keep passing even if that wrapping were deleted
    from pydantic import BaseModel
    from registry.capabilities import CapabilityKind, CapabilityRegistry, ExpertOutput, ExpertRequest, ExpertSpec, ToolSpec
    from registry.capabilities import validate
    from registry.capabilities.handler import ExpertHandler as RealHandler, ToolHandler
    from foundation import PermissionLevel

    class _In(BaseModel):
        prompt: str

    class _Probe:
        wants_workspace = True   # forces _build_env to spin a real workspace
        async def run(self, args, workspace=None):
            return None

    captured: list = []

    class _CaptureEnv:
        async def run(self, args, env):
            captured.append(env)
            return ExpertOutput(summary="ok", full_content="ok", confidence=0.5)

    reg = CapabilityRegistry()
    tspec = ToolSpec(name="probe", kind=CapabilityKind.TOOL, description="p", domain="fs", impl=_Probe,
                      input_schema=_In, output_schema=ExpertOutput, permission=PermissionLevel.READ)
    reg.register(tspec, validate(tspec))
    espec = ExpertSpec(name="fake", kind=CapabilityKind.EXPERT, description="d", domain="dom", impl=_CaptureEnv,
                        input_schema=_In, output_schema=ExpertOutput, skills=("s.md",), tool_grants=("fs.probe",))
    reg.register(espec, validate(espec))

    async def hang(data):
        await asyncio.sleep(10)
        return NS(threat_level=ThreatLevel.NONE, reason=None)
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", hang)
    monkeypatch.setattr("registry.capabilities.handler.experts.settings.EXPERTS",
                         settings.EXPERTS.model_copy(update={"timeout_s": 0.05}))

    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"a.txt": b"hi"})]

    handler = RealHandler(registry=reg, tools=ToolHandler(registry=reg))
    summaries = asyncio.run(handler.run_experts(
        [ExpertRequest(key="dom.fake", arguments={"prompt": "T"})], ctx
    ))

    assert summaries[0].summary == "ok"   # the expert still completes -- not silenced
    env = captured[0]
    assert env.input_files == [] and env.seed_failures == [("repo.zip", "input seeding timed out")]


def test_run_one_degrades_honestly_when_seed_inputs_raises_unexpectedly(monkeypatch):
    # a fault OTHER than BadZipFile/SanitizationError escaping _extract_archive
    # must degrade this one expert's seeding, never propagate out of _run_one and
    # take down every concurrent expert in the same run_experts asyncio.gather
    # (which has no return_exceptions=True)
    from pydantic import BaseModel
    from registry.capabilities import CapabilityKind, CapabilityRegistry, ExpertOutput, ExpertRequest, ExpertSpec, ToolSpec
    from registry.capabilities import validate
    from registry.capabilities.handler import ExpertHandler as RealHandler, ToolHandler
    from foundation import PermissionLevel

    class _In(BaseModel):
        prompt: str

    class _Probe:
        wants_workspace = True
        async def run(self, args, workspace=None):
            return None

    captured: list = []

    class _CaptureEnv:
        async def run(self, args, env):
            captured.append(env)
            return ExpertOutput(summary="ok", full_content="ok", confidence=0.5)

    reg = CapabilityRegistry()
    tspec = ToolSpec(name="probe", kind=CapabilityKind.TOOL, description="p", domain="fs", impl=_Probe,
                      input_schema=_In, output_schema=ExpertOutput, permission=PermissionLevel.READ)
    reg.register(tspec, validate(tspec))
    espec = ExpertSpec(name="fake", kind=CapabilityKind.EXPERT, description="d", domain="dom", impl=_CaptureEnv,
                        input_schema=_In, output_schema=ExpertOutput, skills=("s.md",), tool_grants=("fs.probe",))
    reg.register(espec, validate(espec))

    async def boom(data):
        raise RuntimeError("kaboom - simulated fault deep in the seed path")
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", boom)

    ctx = VrakshaContext.new("s")
    ctx.input_files = [_archive_input({"a.txt": b"hi"})]

    handler = RealHandler(registry=reg, tools=ToolHandler(registry=reg))
    summaries = asyncio.run(handler.run_experts(
        [ExpertRequest(key="dom.fake", arguments={"prompt": "T"})], ctx
    ))

    assert summaries[0].summary == "ok"   # never propagated -- the expert still ran
    env = captured[0]
    assert env.input_files == []
    assert "kaboom" in env.seed_failures[0][1]


def test_attached_files_note_routes_an_archive_to_the_engineering_batch():
    from core.orchestrator.utils.prompt import build_user_prompt

    note = build_user_prompt(
        NS(modality="text", content="understand this codebase"),
        NS(items=[]),
        None,
        [InputFile("repo.zip", "archive", b"x", 1)],
    )
    assert "repo.zip (archive)" in note
    assert "engineering" in note and "spawn the engineering batch" in note
