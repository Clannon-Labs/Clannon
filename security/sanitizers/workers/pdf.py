"""
PDF sanitizer worker.

This module runs after universal pre-sanitization has already scanned the raw
payload with ClamAV/YARA. PDF handling gets extra care because PDFs can contain
active content, embedded files, forms, huge page counts, and malformed object
graphs that are risky to parse downstream.

The worker uses:

* PyMuPDF (`fitz`) for lightweight page-count validation.
* pikepdf for structural parsing and safe re-saving.

The Didier Stevens `pdfid.py` and `pdf-parser.py` files in security/vendors are
standalone forensic scripts. They are useful for manual/deeper analysis, but
they are not imported here because `pdf-parser.py` is not a valid module name
and both scripts are CLI-oriented.
"""

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from foundation import SanitizationError, ThreatLevel, constants


DANGEROUS_PDF_KEYS = {
    "/AA",            # additional actions
    "/AcroForm",      # interactive forms can carry scripts/actions
    "/EmbeddedFile",  # attached files
    "/Filespec",      # file attachment specifications
    "/JavaScript",    # JavaScript name tree/action
    "/JS",            # JavaScript action payload
    "/Launch",        # launch external command/file
    "/OpenAction",    # action that runs when the PDF is opened
    "/RichMedia",     # embedded Flash/media-like content
    "/XFA",           # XML forms architecture
}


@dataclass
class PdfWorkerResult:
    """Internal result returned by one PDF sub-worker."""
    name: str
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    sanitized_pdf: bytes | None = None
    page_count: int | None = None

    @property
    def passed(self) -> bool:
        return not self.threat_level.should_block


@dataclass
class PdfScanResult:
    """Public result returned to security/sanitizers/runner.py."""
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool = True
    sanitized_pdf: bytes | None = None
    page_count: int | None = None


PdfWorker = Callable[[bytes], PdfWorkerResult]


def _payload_to_bytes(pdf: Any) -> bytes:
    """Normalize supported PDF inputs into bytes."""
    if isinstance(pdf, bytes):
        return pdf
    if isinstance(pdf, bytearray):
        return bytes(pdf)
    if isinstance(pdf, memoryview):
        return pdf.tobytes()
    if isinstance(pdf, (str, Path)):
        path = Path(pdf)
        if path.exists() and path.is_file():
            return path.read_bytes()

    raise SanitizationError(
        "PDF sanitizer expected bytes or a PDF file path",
        modality="pdf",
        worker="pdf",
    )


def _has_pdf_header(payload: bytes) -> bool:
    """Return True when the payload starts like a PDF file."""
    return payload.lstrip()[:5] == b"%PDF-"


def _structure_worker(payload: bytes) -> PdfWorkerResult:
    """
    Verify that pikepdf can parse the PDF object graph.

    Encrypted PDFs are blocked because this sanitizer cannot inspect or clean
    their contents without a password.
    """
    if not _has_pdf_header(payload):
        raise SanitizationError(
            "Invalid PDF payload: missing %PDF header",
            modality="pdf",
            worker="pikepdf",
        )

    try:
        import pikepdf

        with pikepdf.Pdf.open(io.BytesIO(payload)) as pdf:
            if pdf.is_encrypted:
                return PdfWorkerResult(
                    name="pikepdf-structure",
                    threat_level=ThreatLevel.HIGH,
                    reason="Encrypted PDF cannot be inspected safely",
                )
    except pikepdf.PasswordError as exc:
        return PdfWorkerResult(
            name="pikepdf-structure",
            threat_level=ThreatLevel.HIGH,
            reason=f"Encrypted PDF cannot be opened: {exc}",
        )
    except Exception as exc:
        raise SanitizationError(
            f"PDF structure validation failed: {exc}",
            modality="pdf",
            worker="pikepdf",
        ) from exc

    return PdfWorkerResult(name="pikepdf-structure")


def _page_count_worker(payload: bytes) -> PdfWorkerResult:
    """
    Count pages and block extremely large PDFs.

    Page count is a resource-safety check. A huge page count can be used to
    create expensive downstream extraction/normalization work.
    """
    try:
        import fitz

        with fitz.open(stream=payload, filetype="pdf") as doc:
            page_count = doc.page_count
    except Exception as exc:
        raise SanitizationError(
            f"PDF page-count validation failed: {exc}",
            modality="pdf",
            worker="pymupdf",
        ) from exc

    if page_count > constants.MAX_PDF_PAGES:
        return PdfWorkerResult(
            name="pymupdf-page-count",
            threat_level=ThreatLevel.HIGH,
            reason=f"PDF exceeds max page count: {page_count}",
            page_count=page_count,
        )

    return PdfWorkerResult(name="pymupdf-page-count", page_count=page_count)


def _strip_dangerous_entries(obj: Any, stripped: set[str], seen: set[int]) -> None:
    """
    Recursively remove dangerous keys from pikepdf dictionaries.

    pikepdf objects can be indirect and cyclic, so `seen` prevents infinite
    recursion. Missing/deleted child objects are ignored because pikepdf may
    expose unusual low-level objects while recovering malformed files.
    """
    object_id = id(obj)
    if object_id in seen:
        return
    seen.add(object_id)

    try:
        import pikepdf

        if isinstance(obj, pikepdf.Dictionary):
            for key in list(obj.keys()):
                key_name = str(key)
                if key_name in DANGEROUS_PDF_KEYS:
                    stripped.add(key_name)
                    del obj[key]
                    continue

                try:
                    _strip_dangerous_entries(obj[key], stripped, seen)
                except Exception:
                    continue

        elif isinstance(obj, pikepdf.Array):
            for item in list(obj):
                _strip_dangerous_entries(item, stripped, seen)
    except Exception:
        return


def _sanitize_worker(payload: bytes) -> PdfWorkerResult:
    """
    Remove active PDF entries and re-save the document.

    Re-saving through pikepdf normalizes the file structure and drops unreferenced
    objects. Dangerous action/form/attachment keys are stripped before saving.
    """
    try:
        import pikepdf

        stripped: set[str] = set()
        with pikepdf.Pdf.open(io.BytesIO(payload)) as pdf:
            _strip_dangerous_entries(pdf.Root, stripped, set())
            for obj in pdf.objects:
                _strip_dangerous_entries(obj, stripped, set())

            output = io.BytesIO()
            pdf.save(
                output,
                encryption=False,
                deterministic_id=True,
                compress_streams=True,
            )
            sanitized_pdf = output.getvalue()
    except Exception as exc:
        raise SanitizationError(
            f"PDF sanitization failed: {exc}",
            modality="pdf",
            worker="pikepdf",
        ) from exc

    if stripped:
        return PdfWorkerResult(
            name="pikepdf-sanitize",
            threat_level=ThreatLevel.MEDIUM,
            reason=f"PDF active content stripped: {', '.join(sorted(stripped))}",
            sanitized_pdf=sanitized_pdf,
        )

    reason = None
    threat_level = ThreatLevel.NONE
    if sanitized_pdf != payload:
        reason = "PDF re-saved and structure normalized"
        threat_level = ThreatLevel.LOW

    return PdfWorkerResult(
        name="pikepdf-sanitize",
        threat_level=threat_level,
        reason=reason,
        sanitized_pdf=sanitized_pdf,
    )


def _highest_threat(results: list[PdfWorkerResult]) -> ThreatLevel:
    """Return the most severe threat level reported by PDF sub-workers."""
    if not results:
        return ThreatLevel.NONE

    order = {
        ThreatLevel.NONE: 0,
        ThreatLevel.LOW: 1,
        ThreatLevel.MEDIUM: 2,
        ThreatLevel.HIGH: 3,
        ThreatLevel.CRITICAL: 4,
    }
    return max((result.threat_level for result in results), key=order.__getitem__)


def _run_worker(worker: PdfWorker, payload: bytes) -> PdfWorkerResult:
    """Run one PDF sub-worker and wrap unexpected errors with context."""
    try:
        return worker(payload)
    except SanitizationError:
        raise
    except Exception as exc:
        worker_name = worker.__name__.removeprefix("_").removesuffix("_worker")
        raise SanitizationError(
            f"PDF sanitizer worker failed: {exc}",
            modality="pdf",
            worker=worker_name,
        ) from exc


def _scan_sync(pdf: Any) -> PdfScanResult:
    """
    Run all PDF sanitizer checks and aggregate their results synchronously.

    The public async scan() function only offloads this blocking work to a
    thread. Keeping the real logic here mirrors the text/image workers and makes
    tests easier to write.
    """
    payload = _payload_to_bytes(pdf)
    results = [
        _run_worker(_structure_worker, payload),
        _run_worker(_page_count_worker, payload),
        _run_worker(_sanitize_worker, payload),
    ]

    threat_level = _highest_threat(results)
    reasons = [result.reason for result in results if result.reason]
    sanitized_pdf = next(
        (result.sanitized_pdf for result in results if result.sanitized_pdf is not None),
        None,
    )
    page_count = next(
        (result.page_count for result in results if result.page_count is not None),
        None,
    )

    return PdfScanResult(
        threat_level=threat_level,
        reason="; ".join(reasons) if reasons else None,
        passed=not threat_level.should_block,
        sanitized_pdf=sanitized_pdf,
        page_count=page_count,
    )


async def scan(pdf: Any) -> PdfScanResult:
    """
    Async entry point used by the sanitizer runner.

    PDF parsing and re-saving are blocking operations, so the synchronous scan
    is offloaded to a thread while the runner awaits all modality workers.
    """
    return await asyncio.to_thread(_scan_sync, pdf)
