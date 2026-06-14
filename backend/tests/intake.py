import asyncio

import pytest

from foundation import Flow, Modality, constants
from core.intake import intake
from core.intake import rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Keep intake tests independent of shared in-process limiter state."""
    rate_limiter._identity_rate_limiter._requests.clear()
    rate_limiter._global_rate_limiter._requests.clear()
    yield


def _run(payload, session):
    return asyncio.run(intake.process(Flow.new(payload, session)))


@pytest.mark.parametrize(
    "payload",
    [
        '{"a": 1, "b": [1, 2]}',          # JSON as text — was wrongly blocked before
        "plain text with a < b && c > d",  # code-ish text must pass
        "こんにちは世界",                    # non-ascii text
    ],
)
def test_text_and_structured_text_accepted(payload):
    out = _run(payload, session=f"ok-{abs(hash(payload))}")
    assert out.status.value == "ok"
    assert out.ctx.detected_modalities == [Modality.TEXT.value]


def test_empty_input_blocks_malformed():
    out = _run("", session="empty")
    assert out.status.value == "blocked"
    assert out.reason == "malformed_input"


def test_oversize_blocks():
    big = "x" * (constants.MAX_INPUT_SIZE_BYTES + 1)
    out = _run(big, session="big")
    assert out.status.value == "blocked"
    assert out.reason == "input_too_large"


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("application/json", Modality.TEXT),
        ("text/markdown", Modality.TEXT),
        ("application/x-empty", Modality.TEXT),
        ("application/pdf", Modality.PDF),
        ("image/png", Modality.IMAGE),
        ("audio/mpeg", Modality.AUDIO),
        ("video/mp4", Modality.VIDEO),
        ("application/zip", None),
        ("application/vnd.ms-excel", None),
    ],
)
def test_modality_from_mime(mime, expected):
    assert intake._modality_from_mime(mime) == expected


def test_str_payload_is_never_read_as_a_path(tmp_path):
    # A str that happens to name a real file must be treated as literal text,
    # never read from disk (arbitrary-file-read guard).
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET CONTENTS")
    out = _run(str(secret), session="pathy")

    assert out.status.value == "ok"
    assert out.ctx.detected_modalities == [Modality.TEXT.value]
    # The forwarded payload is the path string itself, not the file contents.
    assert asyncio.run(out.load()) == str(secret)
