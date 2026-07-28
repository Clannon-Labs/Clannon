"""Hermetic ClamAV adapter-boundary tests; no daemon or network required."""

import pytest

from foundation import SanitizationError, ThreatLevel
from security.sanitizers import pre_sanitization


def _clamd_client(monkeypatch, *, result=None, failure=None):
    class Client:
        def __init__(self, **_kwargs):
            pass

        def instream(self, _stream):
            if failure is not None:
                raise failure
            return result

    monkeypatch.setattr(pre_sanitization.clamd, "ClamdNetworkSocket", Client)


@pytest.mark.parametrize(
    "failure",
    [
        pre_sanitization.clamd.ConnectionError("refused at private scanner endpoint"),
        ConnectionResetError("reset at private scanner endpoint"),
        TimeoutError("timeout at private scanner endpoint"),
        BrokenPipeError("broken pipe at private scanner endpoint"),
    ],
    ids=["refused", "reset", "timeout", "broken-pipe"],
)
def test_clamav_transport_failures_become_safe_sanitization_errors(
    monkeypatch,
    failure,
):
    _clamd_client(monkeypatch, failure=failure)

    with pytest.raises(SanitizationError) as exc_info:
        pre_sanitization.ClamScanner()._scan_sync(b"upload")

    error = exc_info.value
    assert error.args == ("ClamAV scanner was unavailable during the security scan",)
    assert error.modality == "all"
    assert error.worker == "clamav"
    assert error.__cause__ is failure
    assert "private scanner endpoint" not in str(error)


def test_clamav_transport_boundary_does_not_hide_programmer_errors(monkeypatch):
    failure = ValueError("adapter bug")
    _clamd_client(monkeypatch, failure=failure)

    with pytest.raises(ValueError, match="adapter bug") as exc_info:
        pre_sanitization.ClamScanner()._scan_sync(b"upload")

    assert exc_info.value is failure


def test_clamav_clean_result_is_preserved(monkeypatch):
    _clamd_client(monkeypatch, result={"stream": ("OK", None)})

    result = pre_sanitization.ClamScanner()._scan_sync(b"upload")

    assert result.threat_level == ThreatLevel.NONE
    assert result.reason is None
    assert result.passed is True


def test_clamav_malware_result_is_preserved(monkeypatch):
    _clamd_client(
        monkeypatch,
        result={"stream": ("FOUND", "Eicar-Test-Signature")},
    )

    result = pre_sanitization.ClamScanner()._scan_sync(b"upload")

    assert result.threat_level == ThreatLevel.HIGH
    assert result.reason == (
        "ClamAV detected malware signature: Eicar-Test-Signature"
    )
    assert result.signature == "Eicar-Test-Signature"
    assert result.passed is False


def test_clamav_unexpected_response_still_fails_closed(monkeypatch):
    response = {"stream": ("ERROR", "daemon not ready")}
    _clamd_client(monkeypatch, result=response)

    with pytest.raises(
        SanitizationError,
        match="ClamAV returned an unexpected response",
    ) as exc_info:
        pre_sanitization.ClamScanner()._scan_sync(b"upload")

    assert exc_info.value.modality == "all"
    assert exc_info.value.worker == "clamav"
