import asyncio

import pytest

from foundation import Flow, Modality
import settings
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
    big = "x" * (settings.INTAKE.max_input_size_bytes + 1)
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


# --- rate-limit identity: user_id first, session id fallback (issue #18) -----

def _small_limiters(monkeypatch, per_identity=3):
    monkeypatch.setattr(rate_limiter, "_identity_rate_limiter",
        rate_limiter.InMemorySlidingWindowRateLimiter(max_requests=per_identity, window_s=60.0))
    monkeypatch.setattr(rate_limiter, "_global_rate_limiter",
        rate_limiter.InMemorySlidingWindowRateLimiter(max_requests=1000, window_s=60.0))


def test_rate_limit_keys_on_user_id_so_session_rotation_cannot_bypass(monkeypatch):
    """Issue #18: an authed client minting a fresh session id per request must
    NOT reset its budget — the limit keys on user_id when the ctx carries one."""
    _small_limiters(monkeypatch)

    def go(session, user_id):
        return asyncio.run(intake.process(Flow.new("hello world", session, user_id=user_id)))

    for i in range(3):                                     # fresh session EVERY request
        assert go(f"rotated_{i}", "user_A").status.value != "blocked"
    denied = go("rotated_fresh", "user_A")                 # 4th: budget spent, rotation useless
    assert denied.status.value == "blocked" and denied.reason == "rate_limited"

    assert go("any_sess", "user_B").status.value != "blocked"   # other users unaffected


def test_rate_limit_falls_back_to_session_id_for_unauthed(monkeypatch):
    """Pre-auth callers (empty user_id) still get per-session limiting."""
    _small_limiters(monkeypatch)

    def go(session):
        return asyncio.run(intake.process(Flow.new("hello world", session, user_id="")))

    for _ in range(3):
        assert go("anon_sess").status.value != "blocked"
    denied = go("anon_sess")
    assert denied.status.value == "blocked" and denied.reason == "rate_limited"
    assert go("other_sess").status.value != "blocked"      # scoped per session
