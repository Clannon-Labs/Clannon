import asyncio

import pytest

from foundation import SanitizationError, ThreatLevel
from security.sanitizers import pre_sanitization


EICAR_TEST_BYTES = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
    b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)
YARA_MATCH_TEXT = "this text contains a fake yara signature marker"
CLEAN_TEXT = "hello, this is clean text"


@pytest.mark.parametrize("clean_text", [CLEAN_TEXT])
def test_real_yara_scanner_passes_clean_text(tmp_path, clean_text):
    rule_file = tmp_path / "non_matching_rule.yar"
    rule_file.write_text(
        """
rule NonMatchingRule
{
    strings:
        $marker = "this marker is not in the clean input"
    condition:
        $marker
}
""".strip(),
        encoding="utf-8",
    )

    result = asyncio.run(pre_sanitization.YaraScanner(tmp_path).scan(clean_text))
    print("\nreal clean yara result:", result)

    assert result.threat_level == ThreatLevel.NONE
    assert result.reason is None
    assert result.passed is True
    assert result.engine == "yara"
    assert result.skipped is False


@pytest.mark.parametrize("malware_bytes", [EICAR_TEST_BYTES])
def test_real_clamav_scanner_blocks_eicar(malware_bytes):
    try:
        result = asyncio.run(pre_sanitization.ClamScanner().scan(malware_bytes))
    except SanitizationError as exc:
        pytest.skip(f"ClamAV daemon is not available: {exc}")

    print("\nreal clamav eicar result:", result)

    assert result.threat_level == ThreatLevel.HIGH
    assert result.reason is not None
    assert "ClamAV detected malware signature" in result.reason
    assert result.passed is False
    assert result.engine == "clamav"
    assert result.signature is not None


@pytest.mark.parametrize("yara_text", [YARA_MATCH_TEXT])
def test_real_yara_scanner_blocks_matching_rule(tmp_path, yara_text):
    rule_file = tmp_path / "fake_rule.yar"
    rule_file.write_text(
        """
rule FakeRule
{
    strings:
        $marker = "fake yara signature marker"
    condition:
        $marker
}
""".strip(),
        encoding="utf-8",
    )

    result = asyncio.run(pre_sanitization.YaraScanner(tmp_path).scan(yara_text))
    print("\nreal yara match result:", result)

    assert result.threat_level == ThreatLevel.HIGH
    assert result.reason == "YARA matched threat rule(s): FakeRule"
    assert result.passed is False
    assert result.engine == "yara"
    assert result.signature == "FakeRule"


@pytest.mark.parametrize(
    ("raw", "expected_bytes"),
    [
        ("hello", b"hello"),
        (b"already bytes", b"already bytes"),
        (bytearray(b"byte array"), b"byte array"),
    ],
)
def test_payload_to_bytes(raw, expected_bytes):
    result = pre_sanitization._payload_to_bytes(raw)
    print("\npayload bytes result:", result)

    assert result == expected_bytes
