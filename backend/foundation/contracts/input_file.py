"""
InputFile — a user-uploaded file admitted as task input.

An upload is malware-scanned at the boundary, then carried on the context and
seeded into an expert's sandbox workspace so the expert can work on the real file
(read a CSV, run code over a repo). Policy: the scan BLOCKS genuinely malicious
files but does NOT redact or transform clean ones — the bytes here are the
original content, so an expert sees the data with full fidelity. The no-network
sandbox + the output filter contain residual risk.

Thin contract; the scan lives in `security/sanitizers/uploads.py`, the seeding in
the expert handler. Mirrors ArtifactRef (the OUT side) — this is the IN side.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InputFile:
    """One admitted input file: its safe name, modality, and original bytes."""
    name: str          # safe basename the file is seeded under in the workspace
    modality: str      # "text" | "pdf" (what intake's modality map calls it)
    data: bytes        # original, malware-scanned-clean bytes (never redacted)
    size: int          # byte length

    def as_dict(self) -> dict:
        """Metadata only — never the bytes (for the API surface / logs)."""
        return {"name": self.name, "modality": self.modality, "size": self.size}
