"""
Zip-archive validation for a `WorkspacePort` — the shared core `ExpertHandler` builds
on for BOTH directions: an uploaded repo archive going IN (`_extract_archive`) and a
mission's own persisted workspace snapshot going OUT then back IN (`_snapshot_
mission_workspace`/`_restore_mission_workspace`). Split out of `experts.py` (which
was pushing past the 500-line file cap) rather than duplicated — one validator, two
callers, each supplying its own byte cap (a ratio for an upload, an absolute ceiling
for a snapshot — see `settings.SECURITY.archive_max_uncompressed_ratio` vs
`max_workspace_snapshot_bytes`).
"""

from __future__ import annotations

import io
import zipfile

import settings
from foundation import SanitizationError
from security.sanitizers import pre_sanitization


async def validate_archive_members(data: bytes, total_cap: int) -> tuple[list[tuple[str, bytes]], str | None]:
    """Parse+validate a zip's bytes into safe, cap-checked, malware-scanned members.
    All-or-nothing: any cap breach, unsafe member path, or malware hit rejects the
    WHOLE archive, `([], reason)` — nothing written to a workspace by this function
    (writing is `write_members`'s job, kept separate so a caller can validate before
    committing to any disk I/O).

    A zip's own declared `ZipInfo.file_size` is attacker-controlled (or, for a
    self-produced snapshot, simply not to be trusted blindly either), so every cap
    below is checked against bytes actually read off the member, never the declared
    size. Reads `settings.SECURITY.archive_max_entries` + `settings.INTAKE.
    max_input_size_bytes` (per-member cap) — never a local constant, so this can't
    silently drift from the floors it's supposed to enforce."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [], "not a valid zip archive"
    per_member_cap = settings.INTAKE.max_input_size_bytes
    members: list[tuple[str, bytes]] = []
    with zf:
        infos = zf.infolist()
        if len(infos) > settings.SECURITY.archive_max_entries:
            return [], f"{len(infos)} entries exceeds the {settings.SECURITY.archive_max_entries} cap"
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            if not archive_member_is_safe(info.filename):
                return [], f"member {info.filename!r} has an unsafe path"
            try:
                # bounded read: at most one byte past the cap, so a member lying
                # about its own size can never force a huge in-memory decompress
                with zf.open(info) as zef:
                    member_data = zef.read(per_member_cap + 1)
            except Exception:  # noqa: BLE001 — corrupt/unreadable member -> reject the archive
                return [], f"member {info.filename!r} could not be read"
            if len(member_data) > per_member_cap:
                return [], f"member {info.filename!r} exceeds the {per_member_cap}-byte per-file cap"
            total += len(member_data)
            if total > total_cap:
                return [], f"decompressed content exceeds the {total_cap}-byte bomb-guard cap"
            try:
                scan = await pre_sanitization.run(member_data)
            except SanitizationError:
                return [], f"member {info.filename!r} could not be security-scanned"
            if scan.threat_level.should_block:
                return [], f"member {info.filename!r} rejected by the security scan ({scan.reason or 'malicious content'})"
            members.append((info.filename, member_data))
    if not members:
        return [], "archive has no file members (empty or directories only)"
    return members, None


async def write_members(workspace, members: list[tuple[str, bytes]]) -> tuple[list[str], str | None]:
    """Write already-validated `(name, data)` members to a workspace, all-or-nothing."""
    seeded: list[str] = []
    for name, data in members:
        try:
            await workspace.write_bytes(name, data)
        except Exception:  # noqa: BLE001 — validation upstream already screens every
            # realistic escape vector, so this is the rare exceptional case, not the
            # expected path; don't claim a partial repo is the whole repo
            return [], f"member {name!r} could not be written to the workspace"
        seeded.append(name)
    return seeded, None


def mission_workspace_key(mission_id: str, expert_key: str) -> str:
    """The `ArtifactStore` `run_id` a mission's persisted workspace snapshot lives
    under — prefixed (not the bare `mission_id`) so it's structurally distinct from
    a real per-request delivered-artifact folder (`ctx.trace_id`-keyed), and scoped
    by `expert_key` so a future second workspace-having expert can never collide
    with `code.engineer`'s own persisted repo."""
    return f"mission-{mission_id}-{expert_key}"


async def snapshot_workspace(workspace) -> bytes | None:
    """Zip a workspace's full current contents for cross-call persistence — the
    mirror of `validate_archive_members`'s caps, checked on the way OUT instead of
    in. Returns `None` (skip the snapshot) rather than truncating one if the
    workspace exceeds `settings.SECURITY.archive_max_entries` / `max_workspace_
    snapshot_bytes` — a half-written zip would silently corrupt the next restore."""
    try:
        paths = await workspace.list()
    except Exception:  # noqa: BLE001 — a listing fault means no snapshot this call
        return None
    if len(paths) > settings.SECURITY.archive_max_entries:
        return None
    buf = io.BytesIO()
    total = 0
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                data = await workspace.read_bytes(path)
                total += len(data)
                if total > settings.SECURITY.max_workspace_snapshot_bytes:
                    return None
                zf.writestr(path, data)
    except Exception:  # noqa: BLE001 — an IO fault mid-zip means no snapshot this call
        return None
    return buf.getvalue()


def archive_member_is_safe(name: str) -> bool:
    """Zip-slip pre-filter for one archive member's path — mirrors the same rules
    `DockerWorkspace._resolve` enforces (reject empty/absolute/NUL, reject a `..`
    segment), checked here in-memory, before anything is written, so an unsafe
    member aborts the whole archive rather than surfacing as a write failure after
    earlier members are already on disk. `write_bytes`'s own confinement guard
    still runs at write time — this doesn't replace it, just lets the reject
    happen at the right point for an all-or-nothing extraction."""
    if not name or name.startswith("/") or "\x00" in name:
        return False
    return ".." not in name.replace("\\", "/").split("/")
