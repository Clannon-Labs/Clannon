"""
Unified observability for Vraksha: one log file, one decision-log sink.

Every entry point (CLI `main.py`, the FastAPI app, the test harness) calls
`configure_logging()` ONCE at startup so that all traces — module logs
(`core.*`, `registry.*`, `security.*`, `api.*`), library warnings, provider HTTP
calls, AND the orchestrator's structured decision log — land in a single file
(default `backend/logs/clannon.log`, override with `VRAKSHA_LOG_FILE`).

`DecisionLogSink` is the single `ctx.decision_log` replacement used by every caller
that observes a run live. It mirrors each appended entry both to a caller callback
(the TUI activity feed, the API's SSE emitter) AND to that same log file, so the
file is a complete trace of every run — during testing and in normal use. The
pipeline never imports this module; an entry point builds the sink and hands it in
via `pipeline.run(decision_log=...)`, keeping `core/` free of presentation concerns.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, Callable

_DEFAULT_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "logs", "clannon.log"
)

# Third-party loggers that spam at import/startup with no run value. Capped to
# WARNING so the unified log stays a readable trace of actual runs (their warnings
# and errors still come through).
_QUIET_LOGGERS = (
    "presidio-analyzer",
    "presidio_analyzer",
    "watchfiles",
    "python_multipart",
)

_configured = False


def log_path() -> str:
    """The active log file path (env override wins)."""
    return os.getenv("VRAKSHA_LOG_FILE") or _DEFAULT_LOG_PATH


def configure_logging(
    *,
    level: int | str = logging.INFO,
    console: bool = False,
    path: str | None = None,
) -> str:
    """
    Point root logging at a single rotating file. Idempotent — safe to call from
    any entry point; the first call wins, later calls are no-ops and return the
    same path. Call before the pipeline constructs any provider client so the
    whole run is captured.

    level    root level (INFO captures provider HTTP calls + decision log).
    console  also echo to stderr (handy when running tests by hand).
    path     explicit log file (else VRAKSHA_LOG_FILE, else the default).

    Returns the resolved log path.
    """
    global _configured
    target = path or log_path()
    if _configured:
        return target

    os.makedirs(os.path.dirname(target), exist_ok=True)
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    file_handler = RotatingFileHandler(
        target, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    handlers: list[logging.Handler] = [file_handler]

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
        handlers.append(stream)

    root = logging.getLogger()
    root.setLevel(level)
    # Own the single sink: drop handlers other libraries may have installed so
    # everything propagates to our file (their loggers still propagate to root).
    for existing in list(root.handlers):
        root.removeHandler(existing)
    for handler in handlers:
        root.addHandler(handler)

    for noisy in _QUIET_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.captureWarnings(True)  # route warnings.warn(...) into the same file

    _configured = True
    logging.getLogger("clannon").info(
        "logging configured -> %s (level=%s)", target, logging.getLevelName(root.level)
    )
    return target


class DecisionLogSink(list):
    """
    Drop-in `ctx.decision_log` that mirrors every appended entry to (1) the unified
    log file and (2) an optional caller callback (TUI activity feed / SSE emitter).

    This is the single observation seam, replacing the per-caller `_ObservedLog`
    copies the CLI and API used to each define. The pipeline stays unaware of it —
    a caller constructs it and passes it via `pipeline.run(decision_log=...)`. A
    failing observer callback is logged and swallowed so a UI/transport fault never
    takes a run down; the run's own correctness and speed are never sacrificed to
    observation.
    """

    def __init__(self, on_entry: Callable[[Any], None] | None = None) -> None:
        super().__init__()
        self._on_entry = on_entry
        self._log = logging.getLogger("clannon.decision")

    def append(self, entry: Any) -> None:  # the sink only ever appends
        super().append(entry)
        kind = getattr(entry, "kind", "observation")
        message = getattr(entry, "message", entry)
        self._log.info("[%s] %s", kind, str(message))
        if self._on_entry is not None:
            try:
                self._on_entry(entry)
            except Exception:  # noqa: BLE001 — observation must never break a run
                self._log.exception("decision-log observer raised")
