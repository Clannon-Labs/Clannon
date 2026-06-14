import asyncio

import pytest

from foundation import ThreatLevel
from security.sanitizers.workers import text as text_worker


MALICIOUS_SECRET_TEXT = (
    "Please use this test token: "
    "AKIAIOSFODNN7EXAMPLE"
)
MALICIOUS_PII_TEXT = "My email is test@example.com and my phone is 9812345678."
MALICIOUS_HTML_TEXT = "<script>alert(1)</script>Hello"
MALICIOUS_MIXED_TEXT = (
    f"{MALICIOUS_PII_TEXT} {MALICIOUS_SECRET_TEXT} {MALICIOUS_HTML_TEXT}"
)


@pytest.mark.parametrize("malicious_text", [MALICIOUS_MIXED_TEXT])
def test_text_scan_returns_highest_threat_and_combined_reasons(monkeypatch, malicious_text):
    def fake_secrets_worker(text: str) -> text_worker.TextWorkerResult:
        return text_worker.TextWorkerResult(
            name="detect-secrets",
            threat_level=ThreatLevel.HIGH,
            reason="Secret detected: API Key",
        )

    def fake_pii_worker(text: str) -> text_worker.TextWorkerResult:
        return text_worker.TextWorkerResult(
            name="presidio",
            threat_level=ThreatLevel.MEDIUM,
            reason="PII detected: EMAIL_ADDRESS",
            sanitized_text="email: <EMAIL_ADDRESS>",
        )

    monkeypatch.setattr(text_worker, "_secrets_worker", fake_secrets_worker)
    monkeypatch.setattr(text_worker, "_pii_worker", fake_pii_worker)

    result = asyncio.run(text_worker.scan(malicious_text))
    print("scan result:", result)

    assert result.threat_level == ThreatLevel.HIGH
    assert result.passed is False
    assert result.reason == "Secret detected: API Key; PII detected: EMAIL_ADDRESS"


@pytest.mark.parametrize(
    "code_text",
    ["<div>x</div> std::vector<int> v; if (a < b && c > d) return;"],
)
def test_text_scan_does_not_strip_or_escape_html_or_code(monkeypatch, code_text):
    # HTML is no longer stripped/escaped: markup, generics, and comparison
    # operators must survive text sanitization byte-for-byte (no nh3 corruption).
    # Secrets/PII workers are stubbed clean so this isolates the markup behavior.
    monkeypatch.setattr(
        text_worker,
        "_secrets_worker",
        lambda text: text_worker.TextWorkerResult(name="detect-secrets"),
    )
    monkeypatch.setattr(
        text_worker,
        "_pii_worker",
        lambda text: text_worker.TextWorkerResult(name="presidio"),
    )

    result = asyncio.run(text_worker.scan(code_text))
    print("code scan result:", result)

    assert result.threat_level == ThreatLevel.NONE
    assert result.passed is True
    # No safe-replacement payload is produced, so the original text is forwarded
    # verbatim by the runner (no escaping of <, >, & and no tag deletion).
    assert result.sanitized_text is None


@pytest.mark.parametrize("secret_text", [MALICIOUS_SECRET_TEXT])
def test_secrets_worker_flags_test_access_key(secret_text):
    result = text_worker._secrets_worker(secret_text)
    print("secrets worker result:", result)

    assert result.name == "detect-secrets"
    assert result.threat_level == ThreatLevel.HIGH
    assert result.reason is not None
    assert "Secret detected" in result.reason
    assert result.passed is False


@pytest.mark.parametrize(
    ("pii_text", "raw_email"),
    [(MALICIOUS_PII_TEXT, "test@example.com")],
)
def test_pii_worker_flags_and_anonymizes_personal_data(pii_text, raw_email):
    result = text_worker._pii_worker(pii_text)
    print("pii worker result:", result)

    assert result.name == "presidio"
    assert result.threat_level == ThreatLevel.MEDIUM
    assert result.reason is not None
    assert "PII detected" in result.reason
    assert result.sanitized_text is not None
    assert raw_email not in result.sanitized_text
    assert result.passed is True


@pytest.mark.parametrize(
    ("results", "expected_threat"),
    [
        (
            [
                text_worker.TextWorkerResult(name="clean", threat_level=ThreatLevel.NONE),
                text_worker.TextWorkerResult(name="html", threat_level=ThreatLevel.LOW),
                text_worker.TextWorkerResult(name="pii", threat_level=ThreatLevel.MEDIUM),
            ],
            ThreatLevel.MEDIUM,
        )
    ],
)
def test_highest_threat_returns_most_severe_level(results, expected_threat):
    result = text_worker._highest_threat(results)
    print("highest threat result:", result)
    assert result == expected_threat
