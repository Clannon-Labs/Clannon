"""Writer expert: full findings are inlined as source material by ref."""

from registry.capabilities import ExpertFindings
from experts.writer.expert import _materials


def _finding(ref, content, citations=()):
    return ExpertFindings(expert="web.research", ref=ref, full_content=content,
                          citations=list(citations))


def test_materials_inlines_full_findings_with_sources():
    text = _materials(["a1"], [_finding("a1", "DEEP RESEARCH", ["http://x"])])
    assert "DEEP RESEARCH" in text and "http://x" in text and "a1" in text


def test_materials_marks_missing_refs():
    text = _materials(["gone"], [_finding("a1", "DEEP")])
    assert "gone" in text and "not available" in text and "DEEP" not in text


def test_materials_empty_without_refs():
    assert _materials([], [_finding("a1", "DEEP")]) == ""
