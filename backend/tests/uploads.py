"""Upload-IN: boundary scan of uploaded input files + seeding them into the
expert workspace. Policy: block the genuinely malicious, seed the ORIGINAL bytes
(never redact a clean file)."""

import asyncio
import io
import zipfile
from types import SimpleNamespace as NS

import pytest

import settings
from foundation import InputFile, ThreatLevel, VrakshaContext
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.sandbox import DockerWorkspace
from registry.capabilities.handler.support import ExpertEnv, SkillBook
from security.sanitizers import uploads
from core.orchestrator.utils.prompt import build_user_prompt


def _zip_bytes(members: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _clean(monkeypatch):
    async def fake_run(data):
        return NS(threat_level=ThreatLevel.NONE, reason=None)
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", fake_run)


# ---- the boundary scan -----------------------------------------------------


def test_admits_clean_text_with_original_bytes(monkeypatch):
    _clean(monkeypatch)
    raw = b"name,amount\nacme,1200\nbeta,950\n"
    item, reason = asyncio.run(uploads.scan_upload("sales.csv", raw))
    assert reason is None
    assert isinstance(item, InputFile)
    assert item.name == "sales.csv" and item.modality == "text"
    assert item.data == raw and item.size == len(raw)   # original, untouched


def test_filename_is_flattened_to_a_basename(monkeypatch):
    _clean(monkeypatch)
    item, reason = asyncio.run(uploads.scan_upload("../../etc/sales.csv", b"a,b\n1,2\n"))
    assert reason is None and item.name == "sales.csv"


def test_rejects_empty_and_oversized(monkeypatch):
    _clean(monkeypatch)
    item, reason = asyncio.run(uploads.scan_upload("x.csv", b""))
    assert item is None and "empty" in reason

    monkeypatch.setattr(uploads, "_MAX_UPLOAD_BYTES", 8)
    item, reason = asyncio.run(uploads.scan_upload("x.csv", b"way too long"))
    assert item is None and "limit" in reason


def test_rejects_unsupported_binary_type(monkeypatch):
    _clean(monkeypatch)
    # starts with the zip local-file-header signature but isn't a real zip structure
    # (no central directory/EOCD) -- neither sniffs as a known modality nor passes
    # zipfile.is_zipfile, so it stays genuinely out of scope, not just "a bad zip"
    junk = b"PK\x03\x04" + b"\x00" * 64
    item, reason = asyncio.run(uploads.scan_upload("bundle.bin", junk))
    assert item is None and "unsupported" in reason


def test_admits_image_with_original_bytes(monkeypatch):
    _clean(monkeypatch)
    gif = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"      # a minimal GIF — sniffs as image/gif
    item, reason = asyncio.run(uploads.scan_upload("logo.gif", gif))
    assert reason is None
    assert item.modality == "image" and item.data == gif   # original bytes, never nerfed


def test_admits_audio_with_original_bytes(monkeypatch):
    _clean(monkeypatch)
    wav = b"RIFF\x24\x00\x00\x00WAVEfmt "            # sniffs as audio/x-wav
    item, reason = asyncio.run(uploads.scan_upload("voice.wav", wav))
    assert reason is None and item.modality == "audio" and item.data == wav


def test_admits_video_with_original_bytes(monkeypatch):
    _clean(monkeypatch)
    mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"   # sniffs as video/mp4
    item, reason = asyncio.run(uploads.scan_upload("clip.mp4", mp4))
    assert reason is None and item.modality == "video" and item.data == mp4


def test_admits_clean_archive_with_original_bytes(monkeypatch):
    _clean(monkeypatch)
    data = _zip_bytes({"src/main.py": "print('hi')\n", "README.md": "# repo\n"})
    item, reason = asyncio.run(uploads.scan_upload("repo.zip", data))
    assert reason is None
    assert item.modality == "archive" and item.data == data   # original bytes, untouched


def test_rejects_corrupt_or_incomplete_zip(monkeypatch):
    _clean(monkeypatch)
    # a real zip's local-file-header prefix with no central directory/EOCD -- sniffs
    # via the raw signature but fails the zipfile.is_zipfile confirmation, so it never
    # becomes modality "archive" (never reaches the bomb pre-check at all)
    data = _zip_bytes({"a.txt": "hello"})
    truncated = data[: len(data) // 2]
    item, reason = asyncio.run(uploads.scan_upload("bad.zip", truncated))
    assert item is None and "unsupported" in reason


def test_archive_rejects_when_entry_count_exceeds_the_floor(monkeypatch):
    _clean(monkeypatch)
    tight = settings.SECURITY.model_copy(update={"archive_max_entries": 1})
    monkeypatch.setattr(uploads.settings, "SECURITY", tight)
    data = _zip_bytes({"a.txt": "one", "b.txt": "two"})
    item, reason = asyncio.run(uploads.scan_upload("repo.zip", data))
    assert item is None and "entries" in reason


def test_archive_rejects_a_decompression_bomb_by_ratio(monkeypatch):
    _clean(monkeypatch)
    # a highly-compressible member: large declared uncompressed size, tiny compressed
    # bytes -- exactly the zip-bomb shape the ratio guard exists to catch
    data = _zip_bytes({"huge.bin": b"\x00" * 5_000_000})
    tight = settings.SECURITY.model_copy(update={"archive_max_uncompressed_ratio": 5})
    monkeypatch.setattr(uploads.settings, "SECURITY", tight)
    item, reason = asyncio.run(uploads.scan_upload("bomb.zip", data))
    assert item is None and "ratio" in reason


def test_archive_within_the_real_shipped_floors_is_admitted(monkeypatch):
    # proves the real, unmodified settings.SECURITY.archive_* floors (not a test
    # override) admit an ordinary small repo -- the floors aren't accidentally so
    # tight they reject a normal upload
    _clean(monkeypatch)
    data = _zip_bytes({f"src/file_{i}.py": "def f():\n    return 1\n" for i in range(20)})
    item, reason = asyncio.run(uploads.scan_upload("repo.zip", data))
    assert reason is None and item.modality == "archive"


def test_archive_still_goes_through_the_malware_pregate(monkeypatch):
    async def fake_run(data):
        return NS(threat_level=ThreatLevel.HIGH, reason="ClamAV: Eicar-Test-Signature")
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", fake_run)
    data = _zip_bytes({"a.txt": "hello"})
    item, reason = asyncio.run(uploads.scan_upload("repo.zip", data))
    assert item is None and "security scan" in reason


def test_blocks_malicious_content(monkeypatch):
    async def fake_run(data):
        return NS(threat_level=ThreatLevel.HIGH, reason="ClamAV: Eicar-Test-Signature")
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", fake_run)
    item, reason = asyncio.run(uploads.scan_upload("data.csv", b"a,b\n1,2\n"))
    assert item is None and "security scan" in reason and "Eicar" in reason


def test_fails_closed_when_scanner_unavailable(monkeypatch):
    from foundation import SanitizationError

    async def boom(data):
        raise SanitizationError("ClamAV unreachable", modality="all")
    monkeypatch.setattr("security.sanitizers.pre_sanitization.run", boom)
    item, reason = asyncio.run(uploads.scan_upload("data.csv", b"a,b\n1,2\n"))
    assert item is None and "could not be security-scanned" in reason


# ---- seeding into the expert workspace -------------------------------------


class _RecordingWS:
    """Workspace stand-in that records seeded files."""
    def __init__(self):
        self.files = {}
    async def write_bytes(self, rel, data):
        self.files[rel] = data


def _env(ws):
    return ExpertEnv(module_dir=None, model_role="code", skills=SkillBook("/", ()),
                     toolbox=None, granted=[], workspace=ws)


def test_seed_inputs_writes_files_and_records_names():
    ws = _RecordingWS()
    env = _env(ws)
    ctx = VrakshaContext.new("s")
    ctx.input_files = [InputFile("sales.csv", "text", b"a,b\n1,2\n", 8),
                       InputFile("notes.txt", "text", b"hi", 2)]
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx))
    assert ws.files == {"sales.csv": b"a,b\n1,2\n", "notes.txt": b"hi"}
    assert env.input_files == ["sales.csv", "notes.txt"]   # surfaced to the expert


def test_seed_inputs_noop_without_workspace_or_files():
    ctx = VrakshaContext.new("s")
    ctx.input_files = [InputFile("x.csv", "text", b"x", 1)]
    env = _env(None)                                        # no workspace -> nothing seeded
    asyncio.run(ExpertHandler()._seed_inputs(env, ctx))
    assert env.input_files == []

    ws = _RecordingWS()
    env2 = _env(ws)
    empty = VrakshaContext.new("s")                         # ctx with no input files
    asyncio.run(ExpertHandler()._seed_inputs(env2, empty))
    assert ws.files == {} and env2.input_files == []


def test_write_bytes_roundtrips_on_the_real_workspace():
    # file I/O always works (no Docker needed); confirms the seed path end to end
    ws = DockerWorkspace()
    try:
        asyncio.run(ws.write_bytes("data/sales.csv", b"a,b\n1,2\n"))
        assert asyncio.run(ws.read_bytes("data/sales.csv")) == b"a,b\n1,2\n"
    finally:
        asyncio.run(ws.close())


# ---- the orchestrator is told files are attached ---------------------------


def test_user_prompt_names_attached_files():
    note = build_user_prompt(
        NS(modality="text", content="analyze this"),
        NS(items=[]),
        None,
        [InputFile("sales.csv", "text", b"x", 1), InputFile("q3.csv", "text", b"y", 1)],
    )
    assert "ATTACHED FILES" in note and "sales.csv" in note and "q3.csv" in note
    # no attachments -> no note
    plain = build_user_prompt(NS(modality="text", content="hi"), NS(items=[]), None, [])
    assert "ATTACHED FILES" not in plain


def test_user_prompt_routes_a_pdf_to_the_media_expert():
    # a PDF must be steered to the media expert (Gemini reads it), NOT code/data — else
    # the orchestrator sends it to the code sandbox, which can't parse a PDF
    note = build_user_prompt(
        NS(modality="text", content="what does this say?"),
        NS(items=[]),
        None,
        [InputFile("clannon.pdf", "pdf", b"%PDF", 4)],
    )
    assert "clannon.pdf (pdf)" in note            # the modality is surfaced
    assert "media expert" in note                 # and the routing points there
