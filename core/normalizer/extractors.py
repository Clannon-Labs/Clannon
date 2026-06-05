"""
Code-only extractors used by the normalizer layer.

Extractor functions live here when they need heavier libraries or format-
specific logic. The normalizer stage decides when to call them.
"""

from __future__ import annotations

from typing import Any

from .utils import payload_to_bytes


def extract_pdf_pages(payload: Any) -> list[dict[str, Any]]:
    """
    Extract text from a sanitized PDF with PyMuPDF.

    Page boundaries are preserved so later LLM stages can reason over page-local
    context without receiving raw PDF bytes.
    """
    import fitz

    pdf_bytes = payload_to_bytes(payload)
    pages: list[dict[str, Any]] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_index, page in enumerate(doc, start=1):
            pages.append(
                {
                    "page": page_index,
                    "text": page.get_text("text").strip(),
                }
            )
    return pages
