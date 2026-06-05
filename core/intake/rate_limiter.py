"""
Request rate limiting for the intake stage.

This module is intentionally small and backend-shaped. Intake imports the
module-level check_request_rate() helper today, while the limiter class keeps the
door open for a Redis-backed implementation later without changing intake.py.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import threading
import time
from typing import Callable

from foundation import constants


Clock = Callable[[], float]


@dataclass(slots=True, frozen=True)
class RateLimitResult:
    """Decision returned by the intake rate limiter."""
    allowed: bool
    reason: str | None = None


class InMemorySlidingWindowRateLimiter:
    """
    Thread-safe sliding-window request limiter.

    This is fast and good for a single process/container. Production deployments
    with multiple app replicas should replace this backend with Redis while
    keeping the same allow(key) contract.
    """
    def __init__(
        self,
        max_requests: int,
        window_s: float,
        max_tracked_keys: int = constants.RATE_LIMIT_MAX_TRACKED_KEYS,
        clock: Clock = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_s = window_s
        self.max_tracked_keys = max_tracked_keys
        self.clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Return True and record the request when key is inside its limit."""
        now = self.clock()
        cutoff = now - self.window_s

        with self._lock:
            self._prune_if_needed(cutoff)
            if key not in self._requests and len(self._requests) >= self.max_tracked_keys:
                return False
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()

            if len(requests) >= self.max_requests:
                return False

            requests.append(now)
            return True

    def _prune_if_needed(self, cutoff: float) -> None:
        """
        Bound memory growth from many one-off session IDs.

        The scan only runs after the key map reaches max_tracked_keys, so normal
        hot-path requests do not pay for global cleanup.
        """
        if len(self._requests) < self.max_tracked_keys:
            return

        for key in list(self._requests.keys()):
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if not requests:
                del self._requests[key]


_session_rate_limiter = InMemorySlidingWindowRateLimiter(
    max_requests=constants.RATE_LIMIT_MAX_REQUESTS,
    window_s=constants.RATE_LIMIT_WINDOW_S,
)
_global_rate_limiter = InMemorySlidingWindowRateLimiter(
    max_requests=constants.GLOBAL_RATE_LIMIT_MAX_REQUESTS,
    window_s=constants.GLOBAL_RATE_LIMIT_WINDOW_S,
)


def check_request_rate(session_id: str) -> RateLimitResult:
    """
    Check per-session and global intake request limits.

    Per-session is checked first so one noisy session does not consume global
    burst capacity after it is already over its own limit.
    """
    key = session_id or "anonymous"

    if not _session_rate_limiter.allow(key):
        return RateLimitResult(
            allowed=False,
            reason="Session request rate limit exceeded",
        )

    if not _global_rate_limiter.allow("global"):
        return RateLimitResult(
            allowed=False,
            reason="Global request rate limit exceeded",
        )

    return RateLimitResult(allowed=True)
