from core.normalizer import normalizer


def test_scanned_pdf_routes_to_expert(monkeypatch):
    # Image-only PDF: pages exist but carry no text layer.
    monkeypatch.setattr(normalizer, "extract_pdf_pages",
                        lambda payload: [{"page": 1, "text": ""}, {"page": 2, "text": ""}])

    ni = normalizer.normalize_payload(b"%PDF-1.4 fake", modality="pdf")

    assert ni.requires_expert is True
    assert ni.required_capability == "image"
    assert ni.native_payload is not None
    assert not ni.content


def test_text_pdf_is_extracted(monkeypatch):
    monkeypatch.setattr(normalizer, "extract_pdf_pages",
                        lambda payload: [{"page": 1, "text": "hello world"}])

    ni = normalizer.normalize_payload(b"%PDF", modality="pdf")

    assert ni.requires_expert is False
    assert "hello world" in ni.content


def test_text_is_unicode_stabilized():
    # Zero-width space (U+200B) is stripped so downstream scans see canonical
    # text; zero-width joiner (U+200D) is preserved for emoji/complex scripts.
    zwsp, zwj = chr(0x200B), chr(0x200D)
    raw = f"ig{zwsp}nore{zwj} me"
    ni = normalizer.normalize_payload(raw, modality="text")
    assert ni.content == f"ignore{zwj} me"
